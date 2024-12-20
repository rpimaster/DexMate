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
            self.dexcom = Dexcom(username=username, password=password, ous=True)
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
        self.settings_window.geometry("300x350")

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
                    "is_pinned": self.is_pinned  # Save the pin state
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
                    glucose_value = bg.value

                    current_time = datetime.datetime.now()
                    if self.last_reading_time is None or (bg.datetime - self.last_reading_time).total_seconds() >= 60:
                        self.last_reading_time = bg.datetime

                        if self.previous_glucose is not None:
                            delta_value = glucose_value - self.previous_glucose
                        else:
                            delta_value = 0.0

                        #print(f"Delta updated: {delta_value:.2f}")
                        self.delta_label.configure(text=f"Delta: {delta_value:.2f}")
                        self.previous_glucose = glucose_value

                        self.glucose_value.set(f"{glucose_value:.1f}")

                        if self.target_range[0] <= glucose_value <= self.target_range[1]:
                            color = "green"
                        elif glucose_value < self.target_range[0]:
                            color = "red"
                        elif glucose_value > self.target_range[1]:
                            color = "orange"
                        self.glucose_label.configure(fg=color)

                        # Check if the current time is within the snooze period
                        if self.notifications_snoozed_until and datetime.datetime.now() < self.notifications_snoozed_until:
                            return  # Don't trigger notifications if snoozed

                        # Check if the glucose value is out of the target range
                        if glucose_value < self.target_range[0] or glucose_value > self.target_range[1]:
                            self.trigger_notification(glucose_value)

                        if hasattr(bg, 'trend_description') and bg.trend_description is not None:
                            trend_arrow = self.get_trend_arrow(bg.trend_description)
                            self.trend_label.configure(text=trend_arrow)
                        else:
                            self.trend_label.configure(text="Trend N/A")

                    self.update_time_label()

        except AttributeError as e:
            logging.error(f"Dexcom object not initialized or missing attribute: {e}")
        except Exception as e:
            logging.error(f"Error updating labels: {e}")

        self.root.after(1000, self.update_labels)

    def update_time_label(self):
        if self.last_reading_time is not None:
            current_time = datetime.datetime.now()
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

    def trigger_notification(self, glucose_value):
        notification = Notify()
        notification.title = "Glucose Alert"
        notification.message = f"Glucose level is {'low' if glucose_value < self.target_range[0] else 'high'}: {glucose_value} mg/dl"
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
