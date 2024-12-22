import * as assert from 'assert';
import * as vscode from 'vscode';

// Create a type for the exports
export interface ExtensionExports {
    statusBarItem: vscode.StatusBarItem;
}

let _statusBarItem: vscode.StatusBarItem;
let updateInterval: NodeJS.Timeout | undefined;

export function activate(context: vscode.ExtensionContext) {
    // Create status bar item
    _statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );
    context.subscriptions.push(_statusBarItem);

    // ... rest of your activate function ...

    // Return the exports
    return {
        statusBarItem: _statusBarItem
    } as ExtensionExports;
}

// Use _statusBarItem internally instead of statusBarItem
function updateGlucoseData() {
    // Get configuration values
    const config = vscode.workspace.getConfiguration('glucose-monitor');
    const username = config.get<string>('username');
    const password = config.get<string>('password');

    if (!username || !password) {
        _statusBarItem.text = '$(error) Configuration missing';
        _statusBarItem.tooltip = 'Please set username and password in settings';
        _statusBarItem.show();
        return;
    }
    // ... rest of the function, using _statusBarItem instead of statusBarItem ...
}

export function deactivate() {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
}

suite('Extension Test Suite', function() {
    // Increase the timeout for all tests in this suite
    this.timeout(10000); // 10 seconds

    suiteSetup(async () => {
        // Set mock configuration values
        const config = vscode.workspace.getConfiguration('glucose-monitor');
        await config.update('username', 'test-user', true);
        await config.update('password', 'test-password', true);
        await config.update('region', 'ous', true);

        // Ensure extension is activated
        const extension = vscode.extensions.getExtension('undefined_publisher.vscode-dexcom-glucose-monitor');
        if (extension) {
            await extension.activate();
        }
    });

    test('Configuration command registration', async () => {
        const commands = await vscode.commands.getCommands();
        assert.ok(commands.includes('glucose-monitor.configure'));
        assert.ok(commands.includes('glucose-monitor.updateGlucose'));
    });

    test('Status bar item creation', async function() {
        this.timeout(10000); // 10 seconds

        try {
            // Wait for extension to activate
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            const extension = vscode.extensions.getExtension<ExtensionExports>('undefined_publisher.vscode-dexcom-glucose-monitor');
            console.log('Found extension:', extension);
            
            if (!extension) {
                throw new Error('Extension not found! Make sure the extension is loaded properly.');
            }

            // Make sure extension is activated
            if (!extension.isActive) {
                await extension.activate();
            }
            
            const statusBarItem = extension.exports?.statusBarItem;
            console.log('Status bar item:', statusBarItem);
            
            assert.ok(statusBarItem, 'Status bar item should exist');
            assert.ok(
                statusBarItem.text.includes('$(error)') || 
                statusBarItem.text.includes('$(pulse)'),
                'Status bar should show either error or reading'
            );
        } catch (error) {
            console.error('Test failed with error:', error);
            assert.fail(`Test failed: ${error}`);
        }
    });

    test('Configuration settings exist', () => {
        const config = vscode.workspace.getConfiguration('glucose-monitor');
        assert.ok(config.has('username'));
        assert.ok(config.has('password'));
        assert.ok(config.has('region'));
    });

    test('Configuration values are set correctly', async () => {
        const config = vscode.workspace.getConfiguration('glucose-monitor');
        const username = config.get<string>('username');
        const password = config.get<string>('password');
        const region = config.get<string>('region');
        
        assert.strictEqual(username, 'test-user');
        assert.strictEqual(password, 'test-password');
        assert.strictEqual(region, 'ous');
    });

    suiteTeardown(async () => {
        // Clean up configuration
        const config = vscode.workspace.getConfiguration('glucose-monitor');
        await config.update('username', undefined, true);
        await config.update('password', undefined, true);
        await config.update('region', undefined, true);
    });
}); 