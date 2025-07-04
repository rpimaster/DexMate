
# DexMate for VS Code

The **DexMate** extension integrates dexcom blood DexMateing data into your Visual Studio Code environment, providing real-time updates, trend analysis, and notifications directly in the editor.

## Features

- **Real-Time Glucose Readings**: Get your current glucose value displayed in the status bar.
- **Trend Analysis**: Visualize glucose trends over the last 3 hours or the last hour.
- **Custom Alerts**: Configure target ranges and receive alerts for high, low, or rapid changes.
- **Dexcom Integration**: Supports `OUS`, `US`, and `Japan` Dexcom regions.
- **Unit Selection**: Choose between `mmol/L` or `mg/dL` for glucose measurements.
- **Graphical Visualization**: View historical data in an interactive graph.
- **Notifications**: Enable or disable notifications for glucose changes.
- **Factory Reset**: Easily reset your extension settings.

## Installation

1. Open Visual Studio Code.
2. Go to the Extensions view by clicking on the Extensions icon in the Activity Bar or pressing `Ctrl+Shift+X`.
3. Search for `DexMate`.
4. Click **Install**.

## Usage

### Configuration

1. Run the `DexMate: Configure Credentials` command from the Command Palette (`Ctrl+Shift+P`).
2. Enter your Dexcom username and password.
3. Select your region (`OUS`, `US`, or `JP`).
4. Choose your preferred unit (`mmol/L` or `mg/dL`).
5. Set your target glucose range (low and high values).

### Commands

| Command | Description |
|---------|-------------|
| `Update Now` | Fetch the latest glucose reading. |
| `Configure Settings` | Configure Dexcom credentials and preferences. |
| `Show Last Hour` | Display glucose readings for the last hour. |
| `Show Graph` | Open an interactive graph of recent glucose data. |
| `Enable/Disable Notifications` | Toggle notifications. |
| `Factory Reset / Logout` | Reset all settings to default. |

You can access this commands by clicking on the glucose value in the bottom bar of the VS Code.

### Graphs

The `Show Graph` command displays a graph of recent readings with dynamic Y-axis scaling based on your data.

### Notifications

You’ll be alerted when:

- Glucose levels are out of range.
- A significant glucose change occurs (e.g., rapid drops or rises).

Notifications can be enabled or disabled from the menu.

## Development

### Prerequisites

- Visual Studio Code
- Node.js
- Python
- Dexcom credentials

### Troubleshooting

For any issues with the Python integration, ensure:

- `pydexcom` is installed (`pip install pydexcom`).
- Python is added to your system's PATH.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any bugs or features.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Acknowledgements

- It is build using [pydexcom](https://gagebenne.github.io/pydexcom/pydexcom.html) for glucose data integration.
