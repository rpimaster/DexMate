import * as vscode from 'vscode';
import { spawn } from 'child_process';

// Create a type for the exports
export interface ExtensionExports {
	statusBarItem: vscode.StatusBarItem;
}

let _statusBarItem: vscode.StatusBarItem;
let updateInterval: NodeJS.Timeout;
let lastValue: number | null = null;
let lastNotificationTime: string | null = null;

export function activate(context: vscode.ExtensionContext) {
	// Create status bar item
	_statusBarItem = vscode.window.createStatusBarItem(
		vscode.StatusBarAlignment.Right,
		100
	);
	context.subscriptions.push(_statusBarItem);

	// Create command to update glucose
	let disposable = vscode.commands.registerCommand('glucose-monitor.updateGlucose', () => {
		updateGlucoseData();
	});
	context.subscriptions.push(disposable);

	// Add configuration command
	let configureCommand = vscode.commands.registerCommand('glucose-monitor.configure', async () => {
		const username = await vscode.window.showInputBox({
			prompt: 'Enter your Dexcom username',
			placeHolder: 'username'
		});
		
		if (!username) {
			vscode.window.showWarningMessage('Configuration was canceled.');
			return; // Exit early if the user cancels input
		}				
		
		if (username) {
			const password = await vscode.window.showInputBox({
				prompt: 'Enter your Dexcom password',
				password: true
			});
			
			if (password) {
				const region = await vscode.window.showQuickPick(['ous', 'us', 'jp'], {
					placeHolder: 'Select your Dexcom region'
				});
				
				if (region) {
					const unit = await vscode.window.showQuickPick(['mmol', 'mgdl'], {
						placeHolder: 'Select your preferred unit',
						title: 'Glucose Unit'
					});

					if (unit) {
						const targetLow = await vscode.window.showInputBox({
							prompt: `Enter your target low (${unit === 'mmol' ? 'mmol/L' : 'mg/dL'})`,
							placeHolder: unit === 'mmol' ? '4.0' : '72',
							value: unit === 'mmol' ? '4.0' : '72'
						});

						const targetHigh = await vscode.window.showInputBox({
							prompt: `Enter your target high (${unit === 'mmol' ? 'mmol/L' : 'mg/dL'})`,
							placeHolder: unit === 'mmol' ? '10.0' : '180',
							value: unit === 'mmol' ? '10.0' : '180'
						});
						
						const config = vscode.workspace.getConfiguration('glucose-monitor');
						await config.update('username', username, true);
						
						await config.update('password', password, true);
						await config.update('region', region, true);
						await config.update('targetLow', parseFloat(targetLow || '4.0'), true);
						await config.update('targetHigh', parseFloat(targetHigh || '10.0'), true);
						await config.update('unit', unit, true);
						vscode.window.showInformationMessage('Glucose Monitor configured successfully!');
						updateGlucoseData();
					}
				}
			}
		}
	});
	context.subscriptions.push(configureCommand);

	// Initial update
	updateGlucoseData();

	// Update every 5 seconds (5000 milliseconds) instead of every second
	updateInterval = setInterval(updateGlucoseData, 5000);

	_statusBarItem.command = 'glucose-monitor.showMenu';

	let menuCommand = vscode.commands.registerCommand('glucose-monitor.showMenu', async () => {
		const config = vscode.workspace.getConfiguration('glucose-monitor');
		const notificationsEnabled = config.get<boolean>('notifications') ?? true;
		
		const items = [
			'Update Now',
			'Configure Settings',
			'Show Last Hour',
			'Show Graph',
			`${notificationsEnabled ? 'Disable' : 'Enable'} Notifications`,
			'Factory Reset / Logout'
		];
		
		const selection = await vscode.window.showQuickPick(items);
		switch(selection) {
			case 'Update Now':
				updateGlucoseData();
				break;
			case 'Configure Settings':
				vscode.commands.executeCommand('glucose-monitor.configure');
				break;
			case 'Show Last Hour':
				showLastHourReadings();
				break;
			case 'Show Graph':
				vscode.commands.executeCommand('glucose-monitor.showGraph');
				break;
			case 'Enable Notifications':
			case 'Disable Notifications':
				toggleNotifications();
				break;
			case 'Factory Reset / Logout':
				factoryReset();
				break;
		}
	});
	context.subscriptions.push(menuCommand);

	// Add command to show graph
	let graphCommand = vscode.commands.registerCommand('glucose-monitor.showGraph', async () => {
		await GlucoseGraphPanel.createOrShow(context);
	});
	context.subscriptions.push(graphCommand);

	// Return the exports
	return {
		statusBarItem: _statusBarItem
	} as ExtensionExports;
}

function updateGlucoseData() {
	const config = vscode.workspace.getConfiguration('glucose-monitor');
	const username = config.get<string>('username');
	const password = config.get<string>('password');
	const region = config.get<string>('region') || 'ous';

	if (!username || !password) {
		_statusBarItem.text = '$(error) Configuration missing';
		_statusBarItem.tooltip = 'Click to configure Dexcom credentials';
		_statusBarItem.command = 'glucose-monitor.configure'; // Make status bar clickable
		_statusBarItem.show();

		void vscode.window.showWarningMessage(
			'Dexcom Glucose Monitor needs to be configured.',
			'Configure Now'
		).then((selection) => {
			if (selection === 'Configure Now') {
				void vscode.commands.executeCommand('glucose-monitor.configure');
			}
		});	
		return;
	}

	console.log('Starting Python process...');
	const pythonScript = `
import sys
import json
from pydexcom import Dexcom
from datetime import datetime, timedelta

try:
    region = "${region}"
    dexcom = Dexcom(username="${username}", password="${password}", region=region)
    
    # Calculate minutes for the last 3 hours (3 * 60 = 180 minutes)
    minutes = 180
    
    # Get readings for the last 3 hours
    historical_readings = dexcom.get_glucose_readings(minutes)
    
    # Format all readings
    readings = []
    for reading in historical_readings:
        readings.append({
            "value": reading._value / 18.0,
            "trend": str(reading._trend_direction),
            "time": reading._datetime.isoformat() if reading._datetime else None
        })
    
    print(json.dumps({"historical": readings}))

except Exception as e:
    print(f"Error: {str(e)}", file=sys.stderr)
    sys.exit(1)
`;

	const pythonProcess = spawn('python', ['-c', pythonScript]);
	let output = '';
	let errorOutput = '';

	pythonProcess.stdout.on('data', (data) => {
		console.log('Stdout:', data.toString());
		output += data.toString();
	});

	pythonProcess.stderr.on('data', (data) => {
		console.log('Stderr:', data.toString());
		errorOutput += data.toString();
	});

	pythonProcess.on('close', async (code) => {
		console.log(`Process exited with code ${code}`);
		console.log('Output:', output);
		console.log('Errors:', errorOutput);

		if (code === 0 && output.trim()) {
			try {
				const data = JSON.parse(output.trim());
				console.log('Parsed reading:', data);
				
				// Convert values based on unit setting before storing
				const config = vscode.workspace.getConfiguration('glucose-monitor');
				const unit = config.get<string>('unit') || 'mmol';
				
				const convertedReadings = data.historical.map((reading: any) => ({
					...reading,
					value: unit === 'mmol' 
						? Number(reading.value.toFixed(1))
						: Math.round(reading.value * 18.0)
				}));

				// Store the converted readings
				await config.update('lastReadings', convertedReadings, true);

				// Get the most recent reading from historical data
				const latestReading = data.historical[0];
				if (!latestReading) {
					throw new Error('No readings available');
				}

				const currentValue = unit === 'mmol' 
					? parseFloat(latestReading.value)
					: Math.round(parseFloat(latestReading.value) * 18.0);
				const currentTime = latestReading.time;

				// Update status bar with color
				const displayValue = unit === 'mmol' 
					? currentValue.toFixed(1) 
					: Math.round(currentValue).toString();
				
				_statusBarItem.text = `$(pulse) ${displayValue} ${unit === 'mmol' ? 'mmol/L' : 'mg/dL'} ${getTrendArrow(latestReading.trend)}`;
				_statusBarItem.tooltip = `Last reading: ${new Date(currentTime).toLocaleTimeString()}`;
				_statusBarItem.color = new vscode.ThemeColor(getGlucoseColor(currentValue));
				_statusBarItem.show();

				// Handle notifications
				if (shouldNotify(currentValue, currentTime)) {
					const unit = config.get<string>('unit') || 'mmol';
					const displayValue = unit === 'mmol' 
						? currentValue.toFixed(1) 
						: Math.round(currentValue).toString();
					
					let message = `Glucose: ${displayValue} ${unit === 'mmol' ? 'mmol/L' : 'mg/dL'} ${getTrendArrow(latestReading.trend)}`;
					
					const targetHigh = config.get<number>('targetHigh') || (unit === 'mmol' ? 10.0 : 180);
					const targetLow = config.get<number>('targetLow') || (unit === 'mmol' ? 4.0 : 72);
					
					if (currentValue > targetHigh) {
						message += ' (High)';
						vscode.window.showWarningMessage(message);
					} else if (currentValue < targetLow) {
						message += ' (Low)';
						vscode.window.showWarningMessage(message);
					} else if (lastValue && Math.abs(currentValue - lastValue) >= (unit === 'mmol' ? 2.0 : 36)) {
						message += ' (Rapid Change)';
						vscode.window.showWarningMessage(message);
					}

					lastNotificationTime = currentTime;
				}
				lastValue = currentValue;
			} catch (e) {
				console.error('Failed to parse glucose data:', e);
				_statusBarItem.text = '$(error) Parse error';
				_statusBarItem.color = new vscode.ThemeColor('errorForeground');
				_statusBarItem.show();
			}
		} else {
			let errorMessage = errorOutput;
			if (errorOutput.includes('No reading available')) {
				_statusBarItem.text = '$(warning) No recent readings';
				errorMessage = 'No recent glucose readings available. Please check your Dexcom device.';
			} else {
				_statusBarItem.text = '$(error) Glucose data unavailable';
			}
			_statusBarItem.tooltip = errorMessage;
			_statusBarItem.show();
			vscode.window.showWarningMessage(errorMessage);
		}
	});
}

function getTrendArrow(trend: string | undefined): string {
	// First, log what we received
	console.log('getTrendArrow received:', trend);

	// Add null check
	if (!trend) {
		console.log('No trend value provided');
		return '→';  // Default arrow
	}

	// Simple mapping for trend arrows
	switch(trend.toLowerCase()) {
		case 'flat':
			return '→';
		case 'singleup':
		case 'single_up':
			return '↑';
		case 'singledown':
		case 'single_down':
			return '↓';
		case 'fortyfiveup':
		case 'forty_five_up':
			return '↗';
		case 'fortyfivedown':
		case 'forty_five_down':
			return '↘';
		case 'doubleup':
		case 'double_up':
			return '⇈';
		case 'doubledown':
		case 'double_down':
			return '⇊';
		default:
			console.log('Unknown trend:', trend);
			return '→';  // Default to flat arrow instead of question mark
	}
}

function getGlucoseColor(value: number): string {
	const config = vscode.workspace.getConfiguration('glucose-monitor');
	const unit = config.get<string>('unit') || 'mmol';
	const targetHigh = config.get<number>('targetHigh') || (unit === 'mmol' ? 10.0 : 180);
	const targetLow = config.get<number>('targetLow') || (unit === 'mmol' ? 4.0 : 72);

	if (value > targetHigh) { return 'editorWarning.foreground'; }    // High (orange/yellow)
	if (value < targetLow) { return 'errorForeground'; }              // Low (red)
	return 'testing.iconPassed';                                      // Normal (green)
}

function shouldNotify(newValue: number, newTime: string): boolean {
	const config = vscode.workspace.getConfiguration('glucose-monitor');
	const notificationsEnabled = config.get<boolean>('notifications') ?? true;

	if (!notificationsEnabled) { return false; }

	// Only notify if this is a new reading
	if (lastNotificationTime === newTime) {
		return false;
	}

	const unit = config.get<string>('unit') || 'mmol';
	const targetHigh = config.get<number>('targetHigh') || (unit === 'mmol' ? 10.0 : 180);
	const targetLow = config.get<number>('targetLow') || (unit === 'mmol' ? 4.0 : 72);

	// Always notify for out-of-range values on new readings
	if (newValue > targetHigh || newValue < targetLow) {
		return true;
	}

	// For in-range values, check for rapid changes if we have a previous value
	if (lastValue !== null) {
		const significantChange = unit === 'mmol' ? 2.0 : 36;
		return Math.abs(newValue - lastValue) >= significantChange;
	}

	return false;
}

function toggleNotifications() {
	const config = vscode.workspace.getConfiguration('glucose-monitor');
	const currentState = config.get<boolean>('notifications') ?? true;
	config.update('notifications', !currentState, true);
	vscode.window.showInformationMessage(
		`Notifications ${!currentState ? 'enabled' : 'disabled'}`
	);
}

async function showLastHourReadings() {
	const config = vscode.workspace.getConfiguration('glucose-monitor');
	const readings = config.get<Array<{value: number, time: string}>>('lastReadings') || [];
	const unit = config.get<string>('unit') || 'mmol';
	
	const lastHourReadings = readings
		.filter(reading => new Date(reading.time).getTime() > Date.now() - 3600000)
		.map(reading => 
			`${new Date(reading.time).toLocaleTimeString()}: ${reading.value} ${unit === 'mmol' ? 'mmol/L' : 'mg/dL'}`
		);

	if (lastHourReadings.length === 0) {
		vscode.window.showInformationMessage('No readings available for the last hour');
		return;
	}

	vscode.window.showQuickPick(lastHourReadings, {
		placeHolder: 'Last Hour Readings',
		canPickMany: false
	});
}

// This method is called when your extension is deactivated
export function deactivate() {
	if (updateInterval) {
			clearInterval(updateInterval);
	}
}

class GlucoseGraphPanel {
	public static async createOrShow(context: vscode.ExtensionContext) {
		const panel = vscode.window.createWebviewPanel(
			'glucoseGraph',
			'Glucose Readings',
			vscode.ViewColumn.One,
			{ enableScripts: true }
		);

		const config = vscode.workspace.getConfiguration('glucose-monitor');
		const readings = config.get<Array<{
			value: number,
			trend: string,
			time: string
		}>>('lastReadings') || [];

		// Use the stored readings which are already in the correct unit
		panel.webview.html = getWebviewContent({ historical: readings });
	}
}

function getWebviewContent(data: any) {
	const config = vscode.workspace.getConfiguration('glucose-monitor');
	const unit = config.get<string>('unit') || 'mmol';
	const targetLow = config.get<number>('targetLow') || (unit === 'mmol' ? 4.0 : 72);
	const targetHigh = config.get<number>('targetHigh') || (unit === 'mmol' ? 10.0 : 180);

	// Reverse the readings array to show oldest to newest
	const readings = (data.historical || []).reverse();
	const values = readings.map((r: any) => Number(r.value));
	const labels = readings.map((r: any) => new Date(r.time).toLocaleTimeString());

	// Calculate dynamic Y-axis range based on actual values
	const maxGlucose = Math.max(...values);
	const minGlucose = Math.min(...values);
	const yAxisBuffer = unit === 'mmol' ? 4 : 72;
	
	const yMin = Math.max(0, Math.min(minGlucose - yAxisBuffer, targetLow - yAxisBuffer));
	const yMax = Math.max(maxGlucose + yAxisBuffer, targetHigh + yAxisBuffer);

	return `
		<!DOCTYPE html>
		<html>
			<head>
				<title>Glucose Graph</title>
				<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
				<style>
					canvas {
						max-height: 80vh;
						width: 100% !important;
						height: 600px !important;
					}
				</style>
			</head>
			<body>
				<canvas id="glucoseChart"></canvas>
				<script>
					const ctx = document.getElementById('glucoseChart');
					new Chart(ctx, {
						type: 'line',
						data: {
							labels: ${JSON.stringify(labels)},
							datasets: [
								{
									label: 'Target Range',
									data: Array(${labels.length}).fill(${targetHigh}),
									borderColor: 'rgba(255, 0, 0, 0.2)',
									backgroundColor: 'rgba(255, 0, 0, 0.1)',
									fill: '+1',
									pointRadius: 0,
									order: 1
								},
								{
									label: 'Target Range',
									data: Array(${labels.length}).fill(${targetLow}),
									borderColor: 'rgba(255, 0, 0, 0.2)',
									backgroundColor: 'rgba(0, 255, 0, 0.1)',
									fill: false,
									pointRadius: 0,
									order: 1
								},
								{
									label: 'Glucose (${unit === 'mmol' ? 'mmol/L' : 'mg/dL'})',
									data: ${JSON.stringify(values)},
									borderColor: 'rgb(75, 192, 192)',
									borderWidth: 3,  // Increased line thickness
									tension: 0.1,
									fill: false,
									pointRadius: 6,  // Increased point size
									pointHoverRadius: 10,
									order: 0
								}
							]
						},
						options: {
							responsive: true,
							maintainAspectRatio: false,
							scales: {
								y: {
									beginAtZero: false,
									min: ${yMin},
									max: ${yMax},
									title: {
										display: true,
										text: '${unit === 'mmol' ? 'mmol/L' : 'mg/dL'}',
										font: {
											size: 14,
											weight: 'bold'
										}
									},
									ticks: {
										font: {
											size: 12
										}
									}
								},
								x: {
									title: {
										display: true,
										text: 'Time',
										font: {
											size: 14,
											weight: 'bold'
										}
									},
									ticks: {
										font: {
											size: 12
										}
									}
								}
							},
							plugins: {
								legend: {
									display: true,
									position: 'top',
									labels: {
										font: {
											size: 14
										}
									}
								}
							}
						}
					});
				</script>
			</body>
		</html>
	`;
}

interface GlucoseData {
    historical: Array<{
        value: number;
        trend: string;
        time: string | null;
    }>;
}

// Add conversion helper functions
function mgdlToMmol(mgdl: number): number {
    return Number((mgdl / 18.0).toFixed(1));
}

function mmolToMgdl(mmol: number): number {
    return Math.round(mmol * 18.0);
}

async function factoryReset() {
    const confirm = await vscode.window.showWarningMessage(
        'Are you sure you want to reset all settings? This will remove your credentials and all saved data.',
        'Yes, Reset All',
        'Cancel'
    );

    if (confirm === 'Yes, Reset All') {
        const config = vscode.workspace.getConfiguration('glucose-monitor');
        await config.update('username', undefined, true);
        await config.update('password', undefined, true);
        await config.update('region', undefined, true);
        await config.update('unit', 'mmol', true);
        await config.update('targetLow', 4.0, true);
        await config.update('targetHigh', 10.0, true);
        await config.update('notifications', true, true);
        await config.update('lastReadings', [], true);

        vscode.window.showInformationMessage('All settings have been reset.');
        updateGlucoseData(); // This will trigger the configuration missing notification
    }
}
