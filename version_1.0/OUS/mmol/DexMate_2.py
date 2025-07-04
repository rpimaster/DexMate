# MIT License
# 
# Copyright (c) 2024 rpimaster
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import tkinter as tk
from tkinter import messagebox
import json
import datetime
import logging
from pydexcom import Dexcom
from notifypy import Notify
from cryptography.fernet import Fernet
import os
import stat
import sqlite3
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split, GridSearchCV, KFold
import numpy as np
import threading

class GlucoseWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("DexMate")
        self.root.geometry("300x215")

        self.label = tk.Label(root, text="Glucose Level:")
        self.label.pack(pady=5)

        self.glucose_value = tk.StringVar()
        self.glucose_label = tk.Label(root, textvariable=self.glucose_value, font=("Helvetica", 22))
        self.glucose_label.pack()

        self.trend_label = tk.Label(root, text="", font=("Helvetica", 22))
        self.trend_label.pack(pady=5)

        self.time_label = tk.Label(root, text="", font=("Helvetica", 12))
        self.time_label.pack(pady=5)

        self.delta_label = tk.Label(root, text="", font=("Helvetica", 12))
        self.delta_label.pack(pady=5)

        # Initialize prediction-related variables EARLY
        self.show_prediction = False  # Add this here
        self.prediction_model = None
        self.prediction_label = tk.Label(root, text="", font=("Helvetica", 12))
        self.prediction_label.pack(pady=2)

        self.target_range = (3.9, 12.0)  # Default target range
        self.last_reading_time = None  # Initialize last reading time to NONE
        self.dexcom = None  # Initialize dexcom object to None
        self.login_window_created = False  # Initialize login_window_created attribute
        self.previous_glucose = None
        self.notifications_snoozed_until = None  # To track the snooze status

        self.locations = [self.set_top_left, self.set_bottom_left, self.set_bottom_right, self.set_top_right]
        self.current_location = 0

        # Create a frame for the buttons
        self.button_frame = tk.Frame(root)
        self.button_frame.pack(pady=5)  # Add padding around the frame

        # Create a button for changing widget location
        self.location_button = tk.Button(self.button_frame, text="Change Location", command=self.change_location)
        self.location_button.pack(side="left", padx=10)  # Pack left with some padding

        # Create a settings button
        self.settings_button = tk.Button(self.button_frame, text="Settings", command=self.open_settings)
        self.settings_button.pack(side="left", padx=10)  # Pack left with some padding

        # Initialize file paths
        self.key_file_path = self.get_file_path('secret.key')
        self.credentials_file_path = self.get_file_path('credentials.json')
        self.settings_file_path = self.get_file_path('settings.json')

        # Load saved settings
        self.load_target_range_and_ous_setting()

        # Load the last saved position
        self.load_last_position()

        self.load_target_range_and_ous_setting()
        self.load_last_position()
        self.load_prediction_setting()  # Add this here

        self.setup_database()  # Initialize database tables

        # Initial update of labels
        self.update_labels()
        self.schedule_update()  # Schedule periodic updates

        # Check if credentials are already saved, if not, show the login window
        self.check_saved_credentials()

        # Variable to track the pin state
        self.is_pinned = False

        # Bind the window close event to save the position
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # Function to set file permissions to read/write only by the user (600)
    def set_file_permissions(self, file_path):
        os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)  # chmod 600

    # Use a directory in the user's home for saving credentials and key files
    def get_file_path(self, filename):
        home_directory = os.path.expanduser("~")  # Get the home directory
        config_directory = os.path.join(home_directory, "Library", "Application Support", "DexMate")  # macOS specific path

        # Create the directory if it doesn't exist
        if not os.path.exists(config_directory):
            os.makedirs(config_directory, exist_ok=True)

        return os.path.join(config_directory, filename)

    def toggle_pin_on_top(self):
        self.is_pinned = not self.is_pinned
        self.root.wm_attributes("-topmost", self.is_pinned)
        self.pin_on_top_button.config(text="Unpin" if self.is_pinned else "Pin on Top")

    def check_saved_credentials(self):
        credentials = self.get_saved_credentials()
        if credentials and credentials.get("username") and credentials.get("password"):
            # Stored credentials exist, attempt authentication
            self.authenticate_dexcom(credentials["username"], credentials["password"])
        else:
            # No stored or incomplete credentials found, show the login window
            self.show_login_window()

    def generate_key(self):
        key = Fernet.generate_key()
        with open(self.key_file_path, 'wb') as key_file:
            key_file.write(key)
        self.set_file_permissions(self.key_file_path)  # Restrict permissions
        return key

    def load_key(self):
        try:
            with open(self.key_file_path, 'rb') as key_file:
                key = key_file.read()
            return key
        except FileNotFoundError:
            return self.generate_key()

    def encrypt_credentials(self, credentials):
        key = self.load_key()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(json.dumps(credentials).encode())
        return encrypted

    def decrypt_credentials(self, encrypted_credentials):
        key = self.load_key()
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_credentials).decode()
        return json.loads(decrypted)

    def get_saved_credentials(self):
        try:
            if not os.path.exists(self.credentials_file_path) or os.path.getsize(self.credentials_file_path) == 0:
                return None
            with open(self.credentials_file_path, 'rb') as file:
                encrypted_credentials = file.read()
                if not encrypted_credentials:
                    return None
                credentials = self.decrypt_credentials(encrypted_credentials)
                return credentials
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
        except Exception as e:
            logging.error(f"Unexpected error reading credentials: {e}")
            return None

    def save_credentials(self, username, password):
        credentials = {"username": username, "password": password}
        encrypted_credentials = self.encrypt_credentials(credentials)

        # Save encrypted credentials to the specified path
        with open(self.credentials_file_path, 'wb') as file:
            file.write(encrypted_credentials)
        self.set_file_permissions(self.credentials_file_path)  # Restrict permissions

    def load_saved_settings(self):
        try:
            with open(self.settings_file_path, 'r') as settings_file:
                settings = json.load(settings_file)
                return settings  # Return the loaded settings dictionary
        except FileNotFoundError:
            return None

    # Function to load target range and ous_setting from saved settings
    def load_target_range_and_ous_setting(self):
        saved_settings = self.load_saved_settings()
        if saved_settings:
            min_value = saved_settings.get("min_value")
            max_value = saved_settings.get("max_value")
            ous_setting = saved_settings.get("ous_setting")
            opacity = saved_settings.get("opacity", 0.8)  # Default opacity to 0.8 if not found
            if min_value is not None and max_value is not None:
                self.target_range = (min_value, max_value)  # Set the target range
            self.ous_setting = ous_setting  # Set the OUS setting
            self.opacity = opacity  # Set the opacity
            self.root.attributes('-alpha', self.opacity)  # Apply the opacity
            return min_value, max_value, ous_setting, opacity
        return None, None, None, 0.8

    def show_login_window(self):
        if not self.login_window_created:
            self.login_window = tk.Toplevel(self.root)
            self.login_window.title("Login")

            self.username_label = tk.Label(self.login_window, text="Username")
            self.username_label.pack()

            self.username_entry = tk.Entry(self.login_window)
            self.username_entry.pack()

            self.password_label = tk.Label(self.login_window, text="Password")
            self.password_label.pack()

            self.password_entry = tk.Entry(self.login_window, show="*")
            self.password_entry.pack()

            self.login_button = tk.Button(self.login_window, text="Login", command=self.login)
            self.login_button.pack()

            self.login_window_created = True

    def authenticate_dexcom(self, username, password):
        try:
            #self.dexcom = Dexcom(username, password, ous=True)
            self.dexcom = Dexcom(username=username, password=password, region="ous")
            self.update_labels()
            self.schedule_update()
        except ConnectionError as e:
            logging.error(f"Error connecting to Dexcom service: {e}")
            # Inform the user about a connection issue
            messagebox.showerror("Connection Error", "Could not connect to Dexcom service.")
        except Exception as e:
            self.dexcom = None
            logging.error(f"Unexpected error during authentication: {e}")
            # Handle any other unexpected errors
            messagebox.showerror("Error", "An unexpected error occurred during authentication.")

    def login(self):
        if isinstance(self.username_entry, tk.Entry) and isinstance(self.password_entry, tk.Entry):
            username = self.username_entry.get()
            password = self.password_entry.get()

            if username and password:
                self.authenticate_dexcom(username, password)
                self.save_credentials(username, password)
                # Clear the Entry widgets after successful login
                self.username_entry.delete(0, 'end')
                self.password_entry.delete(0, 'end')
                self.login_window.destroy()
            else:
                messagebox.showerror("Input Error", "Both username and password are required.")

    def open_settings(self):
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Settings")
        self.settings_window.geometry("300x300")

        target_range_label = tk.Label(self.settings_window, text="Set Target Range:")
        target_range_label.pack()

        self.new_min_entry = tk.Entry(self.settings_window)
        self.new_min_entry.pack()
        self.new_min_entry.insert(0, str(self.target_range[0]))  # Display current min value

        self.new_max_entry = tk.Entry(self.settings_window)
        self.new_max_entry.pack()
        self.new_max_entry.insert(0, str(self.target_range[1]))  # Display current max value

        opacity_label = tk.Label(self.settings_window, text="Set Opacity (0.0 - 1.0):")
        opacity_label.pack()

        self.opacity_entry = tk.Entry(self.settings_window)
        self.opacity_entry.pack()
        self.opacity_entry.insert(0, str(self.opacity))  # Display current opacity value

        save_button = tk.Button(self.settings_window, text="Save Settings", command=self.save_settings)
        save_button.pack(pady=5)

        # Create a button for manually updating the glucose reading
        self.update_button = tk.Button(self.settings_window, text="Manually update", command=self.update_labels)
        self.update_button.pack(pady=5)

        # Create a button to toggle "pin on top"
        pin_text = "Unpin" if self.is_pinned else "Pin on Top"
        self.pin_on_top_button = tk.Button(self.settings_window, text=pin_text, command=self.toggle_pin_on_top)
        self.pin_on_top_button.pack(pady=5)

        # Create a button to snooze notifications
        snooze_button = tk.Button(self.settings_window, text="Snooze Notifications", command=self.snooze_notifications)
        snooze_button.pack(pady=5)

        logout_button = tk.Button(self.settings_window, text="Logout", command=self.logout)
        logout_button.pack(pady=5)

         # Add prediction toggle
        self.prediction_toggle_var = tk.BooleanVar(value=self.show_prediction)
        prediction_toggle = tk.Checkbutton(
            self.settings_window, 
            text="Show Predictions", 
            variable=self.prediction_toggle_var,
            command=self.toggle_prediction
        )
        prediction_toggle.pack(pady=5)

    def toggle_prediction(self):
        self.show_prediction = self.prediction_toggle_var.get()
        if not self.show_prediction:
            self.prediction_label.config(text="")
        self.save_settings()

    def load_prediction_setting(self):
        saved_settings = self.load_saved_settings()
        if saved_settings:
            self.show_prediction = saved_settings.get("show_prediction", False)

    def setup_database(self):
        conn = sqlite3.connect(self.get_file_path('glucose_predictions.db'))
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Prediction (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER UNIQUE,
                glucose REAL,
                predicted_glucose REAL,
                source TEXT,
                note TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def insert_prediction(self, timestamp, glucose, predicted_glucose, source="AI Model", note=""):
        conn = sqlite3.connect(self.get_file_path('glucose_predictions.db'))
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO Prediction 
            (timestamp, glucose, predicted_glucose, source, note)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, glucose, predicted_glucose, source, note))
        conn.commit()
        conn.close()

    # Fetch glucose history from the SQLite database
    def load_glucose_history(self):
        conn = sqlite3.connect(self.get_file_path('glucose_predictions.db'))
        cursor = conn.cursor()
        cursor.execute('SELECT glucose, timestamp, source FROM Prediction ORDER BY timestamp ASC')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return [], [], []

        glucose_history = []
        time_history = []
        trend_history = []

        for row in rows:
            glucose_history.append(row[0])
            source = row[2]
            trend = 1 if "rising" in source else -1 if "falling" in source else 0
            trend_history.append(trend)
            time_history.append(row[1])

        return glucose_history, time_history, trend_history
        
    def build_feature_matrix(glucose_history, time_history, trend_history, delta_history):
        min_required_length = 10  # For example, assume we need at least 10 samples for a feature set
        
        # Check if each history list has the required number of elements
        if (
            len(glucose_history) < min_required_length or 
            len(time_history) < min_required_length or 
            len(trend_history) < min_required_length or 
            len(delta_history) < min_required_length
        ):
            raise ValueError("Not enough data in history to build feature matrix. Minimum required length is 10.")
        
        # Now build the feature matrix safely
        feature_matrix = []
        for i in range(min_required_length, len(glucose_history)):
            glucose_1 = glucose_history[i - 1]
            glucose_2 = glucose_history[i - 2]
            trend = trend_history[i - 1]
            delta = delta_history[i - 1]
            time = time_history[i]
            hour_of_day = (time % 24)
            day_of_week = (time // 24) % 7
            is_weekend = 1 if day_of_week >= 5 else 0

            # Append feature set for current time step
            features = [
                time,
                trend,
                delta,
                hour_of_day,
                day_of_week,
                is_weekend,
                glucose_1,
                glucose_2,
                glucose_1 - glucose_2
            ]
            feature_matrix.append(features)

        return np.array(feature_matrix)

    # Train and tune model
    def train_glucose_model(features, target):
        print(f"Training: features length = {features.shape[0]}, target length = {len(target)}")
        
        # Check that there are enough samples for cross-validation
        if len(target) < 3:
            print("Insufficient samples for 3-fold cross-validation; need at least 3 samples.")
            return None
        
        model = GradientBoostingRegressor()
        param_grid = {
            'n_estimators': [50, 100, 200],
            'learning_rate': [0.01, 0.1, 0.2],
            'max_depth': [3, 5, 7],
            'subsample': [0.8, 1.0]
        }

        # Use cross-validation with n_splits=2 if we only have two samples, otherwise use 3-fold
        n_splits = min(3, len(target))
        cv = KFold(n_splits=n_splits)
        grid_search = GridSearchCV(model, param_grid, cv=cv, scoring='neg_mean_squared_error', verbose=1)
        grid_search.fit(features, target)
        return grid_search.best_estimator_

    # Predict future glucose using the trained model
    def predict_future_glucose(model, time_steps_ahead, current_time, trend, delta, glucose_1, glucose_2):
        hour_of_day = (current_time % 24) + time_steps_ahead * 5 // 60
        day_of_week = ((current_time // 24) % 7)
        is_weekend = 1 if day_of_week >= 5 else 0
        future_features = np.array([[current_time, trend, delta, hour_of_day, day_of_week, is_weekend, glucose_1, glucose_2, glucose_1 - glucose_2]])
        return model.predict(future_features)[0]

    # Define a minimum data requirement
    MIN_DATA_LENGTH = 10  # Minimum samples needed for training

    def update_prediction(self, current_glucose, trend):
        if not self.show_prediction or not current_glucose:
            self.prediction_label.config(text="Predictions disabled")
            return
        
        print(f"Attempting prediction with {len(self.load_glucose_history()[0])} records")

        # Define train_and_predict INSIDE the method to get proper self reference
        def train_and_predict():
            try:
                glucose_history, time_history, trend_history = self.load_glucose_history()
                    
                if len(glucose_history) < 10:
                    self.root.after(0, lambda: self.prediction_label.config(text="Need 10+ readings"))
                    return
                    
                # Prepare features and target
                X = []
                y = []
                for i in range(2, len(glucose_history)):
                    X.append([
                        glucose_history[i-1],
                        glucose_history[i-2],
                        trend_history[i-1],
                        (time_history[i-1] - time_history[i-2])/60
                    ])
                    y.append(glucose_history[i])
                
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
                
                # Train model
                model = GradientBoostingRegressor(n_estimators=100, learning_rate=0.1)
                model.fit(X_train, y_train)
                
                # Make prediction
                current_time = int(datetime.datetime.now().timestamp())
                last_time = time_history[-1]
                minutes_diff = (current_time - last_time) / 60
                prediction = model.predict([[current_glucose, glucose_history[-1], 
                                        trend, minutes_diff]])[0]
                
                 # Update UI
                self.root.after(0, lambda: self.prediction_label.config(
                    text=f"Predicted: {prediction:.1f} mmol/L"
                ))
                self.insert_prediction(
                    timestamp=int(datetime.datetime.now().timestamp()),
                    glucose=current_glucose,
                    predicted_glucose=prediction,
                    source=f"Prediction update {trend}"
                )
            except Exception as e:
                logging.error(f"Prediction error: {e}")

        # Start the thread
        threading.Thread(target=train_and_predict).start()
    
    def logout(self):
        try:
            # Check if the credentials file exists
            if os.path.exists(self.credentials_file_path):
                # If the file exists, delete it to effectively "logout" the user
                os.remove(self.credentials_file_path)

            # Clear the Dexcom and previous glucose values
            self.dexcom = None
            self.previous_glucose = None

            # Show the login window
            self.show_login_window()

        except FileNotFoundError:
            logging.error("Credentials file not found!")
            self.show_login_window()
        except json.JSONDecodeError:
            logging.error("Error decoding JSON from credentials file!")
            self.show_login_window()
        except Exception as e:
            logging.error(f"Unexpected error during logout: {e}")
            self.show_login_window()

    def save_settings(self):
        new_min = self.new_min_entry.get()
        new_max = self.new_max_entry.get()
        new_opacity = self.opacity_entry.get()

        try:
            new_min = float(new_min)
            new_max = float(new_max)
            new_opacity = float(new_opacity)

            if new_min < new_max and 0.0 <= new_opacity <= 1.0:
                self.target_range = (new_min, new_max)
                self.opacity = new_opacity
                self.root.attributes('-alpha', self.opacity)  # Apply the new opacity
                self.is_pinned = self.root.wm_attributes("-topmost")
                self.settings_window.destroy()

                settings = {
                    "min_value": new_min,
                    "max_value": new_max,
                    "opacity": self.opacity,
                    "is_pinned": self.is_pinned,  # Save the pin state
                    "show_prediction": self.show_prediction
                }

                with open(self.settings_file_path, 'w') as settings_file:
                    json.dump(settings, settings_file)
                self.set_file_permissions(self.settings_file_path)  # Restrict permissions
            else:
                messagebox.showerror("Invalid Range or Opacity", "Ensure minimum value is less than maximum value and opacity is between 0.0 and 1.0.")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers for the target range and opacity.")

    def update_labels(self):
        glucose_value = None
        bg = None
        color = "black"

        try:
            if self.dexcom:
                bg = self.dexcom.get_current_glucose_reading()

                if bg is not None:
                    current_time = datetime.datetime.now().astimezone()
                    new_reading = False

                    # Check if this is a new reading (at least 1 minute since last)
                    if self.last_reading_time is None or (bg.datetime.astimezone() - self.last_reading_time).total_seconds() >= 60:
                        new_reading = True
                        glucose_value = bg.mmol_l
                        
                        # Store actual reading in database
                        self.insert_prediction(
                            timestamp=int(current_time.timestamp()),
                            glucose=glucose_value,
                            predicted_glucose=glucose_value,
                            source="Actual reading",
                            note=""
                        )

                        # Update display values
                        if self.previous_glucose is not None:
                            delta_value = glucose_value - self.previous_glucose
                        else:
                            delta_value = 0.0

                        self.delta_label.configure(text=f"Delta: {delta_value:.2f}")
                        self.previous_glucose = glucose_value
                        self.glucose_value.set(f"{glucose_value:.1f}")

                        # Update color based on target range
                        if self.target_range[0] <= glucose_value <= self.target_range[1]:
                            color = "green"
                        elif glucose_value < self.target_range[0]:
                            color = "red"
                        else:
                            color = "orange"
                        self.glucose_label.configure(fg=color)

                        # Update trend arrow
                        if hasattr(bg, 'trend_description') and bg.trend_description is not None:
                            trend_arrow = self.get_trend_arrow(bg.trend_description)
                            self.trend_label.configure(text=trend_arrow)
                        else:
                            self.trend_label.configure(text="Trend N/A")

                        self.last_reading_time = bg.datetime.astimezone()

                    # Always update time label and prediction
                    self.update_time_label()
                    if new_reading:
                        self.update_prediction(glucose_value, self.get_trend_value(bg.trend_description))

                    # Check notifications (even if not new reading)
                    if new_reading and not (self.notifications_snoozed_until and datetime.datetime.now() < self.notifications_snoozed_until):
                        if glucose_value < self.target_range[0] or glucose_value > self.target_range[1]:
                            self.trigger_notification(glucose_value)

        except AttributeError as e:
            logging.error(f"Dexcom object error: {e}")
        except Exception as e:
            logging.error(f"General update error: {e}")

        self.root.after(5000, self.update_labels)  # Check every 5 seconds instead of 1

    def update_time_label(self):
        if self.last_reading_time is not None:
            current_time = datetime.datetime.now().astimezone()  # Convert to aware datetime
            time_diff = current_time - self.last_reading_time
            minutes_diff = int(time_diff.total_seconds() // 60)
            self.time_label.configure(text=f"{minutes_diff} minutes ago")

    def get_trend_arrow(self, trend_description):
        arrows = {
            "rising quickly": "↑↑",
            "rising": "↑",
            "rising slightly": "↗",
            "steady": "→",
            "falling slightly": "↘",
            "falling": "↓",
            "falling quickly": "↓↓",
            "unable to determine trend": "?",
        }
        return arrows.get(trend_description.lower(), "→")
    
    def get_trend_value(self, trend_description):
        trend_values = {
            "rising quickly": 2,
            "rising": 1,
            "rising slightly": 0.5,
            "steady": 0,
            "falling slightly": -0.5,
            "falling": -1,
            "falling quickly": -2,
        }
        return trend_values.get(trend_description.lower(), 0)

    def trigger_notification(self, glucose_value):
        notification = Notify()
        notification.title = "Glucose Alert"
        notification.message = f"Glucose level is {'low' if glucose_value < self.target_range[0] else 'high'}: {glucose_value} mmol/l"
        notification.send()

    def snooze_notifications(self):
        snooze_duration = 15  # Snooze duration in minutes
        self.notifications_snoozed_until = datetime.datetime.now() + datetime.timedelta(minutes=snooze_duration)
        messagebox.showinfo("Snooze Notifications", f"Notifications snoozed for {snooze_duration} minutes.")
        self.settings_window.destroy()

    def change_location(self):
        self.current_location = (self.current_location + 1) % len(self.locations)
        self.locations[self.current_location]()

    def set_top_left(self):
        self.root.geometry("+0+0")

    def set_bottom_left(self):
        taskbar_height = 72  # Adjust this based on the actual taskbar height on the user's system
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"+0+{screen_height - self.root.winfo_height() - taskbar_height}")

    def set_bottom_right(self):
        taskbar_height = 72  # Adjust this based on the actual taskbar height on the user's system
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"+{screen_width - self.root.winfo_width()}+{screen_height - self.root.winfo_height() - taskbar_height}")

    def set_top_right(self):
        screen_width = self.root.winfo_screenwidth()
        window_width = self.root.winfo_width()
        self.root.geometry(f"+{screen_width - window_width}+0")

    def on_close(self):
        self.save_last_position()
        self.root.destroy()

    def save_last_position(self):
        position = self.root.geometry()
        settings = self.load_saved_settings() or {}
        settings["last_position"] = position

        with open(self.settings_file_path, 'w') as settings_file:
            json.dump(settings, settings_file)
        self.set_file_permissions(self.settings_file_path)  # Restrict permissions

    def load_last_position(self):
        settings = self.load_saved_settings()
        if settings and "last_position" in settings:
            self.root.geometry(settings["last_position"])

    def schedule_update(self):
        self.root.after(1000, self.update_labels)

if __name__ == "__main__":
    root = tk.Tk()
    app = GlucoseWidget(root)
    root.mainloop()
