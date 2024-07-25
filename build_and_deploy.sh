#!/bin/bash

# Default values
repo_url="https://github.com/MusilyApp/musily"
clone_dir="musily"
apk_dir="$clone_dir/build/app/outputs/apk/release"
output_apk="musily"
version="unknown"

# Function to show script usage
usage() {
  echo "Usage: $0 --chat <chat_id>"
  echo "       -c <chat_id>"
  exit 1
}

# Process arguments
while [[ "$#" -gt 0 ]]; do
  case $1 in
    -c|--chat) chat_id="$2"; shift ;;
    *) echo "Unknown argument: $1"; usage ;;
  esac
  shift
done

# Check if the chat_id was provided
if [ -z "$chat_id" ]; then
  echo "Error: Chat ID not provided."
  usage
fi

# Clone the repository if it does not exist
if [ ! -d "$clone_dir" ]; then
  git clone "$repo_url" "$clone_dir"
fi

# Navigate to the cloned directory
cd "$clone_dir" || { echo "Error: Failed to navigate to $clone_dir"; exit 1; }

# Run Flutter commands
flutter pub get
flutter build apk

# Move up one directory
cd .. || { echo "Error: Failed to move up one directory"; exit 1; }

# Set version from pubspec.yaml
version=$(grep 'version:' "$clone_dir/pubspec.yaml" | awk '{print $2}' | awk -F'+' '{print $1}')

# Move the APK to the new location
if [ -f "$apk_dir/app-release.apk" ]; then
  mv "$apk_dir/app-release.apk" "$output_apk-$version.apk"
else
  echo "Error: APK file not found."
  exit 1
fi

# Extract the corresponding description from CHANGELOG.md
description=$(awk '/^##[[:blank:]]*'"${version}"'[[:blank:]]*$/ { flag=1; next } flag && /^##/ { flag=0 } flag { buffer=buffer $0 "\n" } END { print buffer }' "$clone_dir/CHANGELOG.md")

# Check if the description was found
if [ -z "$description" ]; then
  echo "Description not found in $changelog_path for version $version"
  exit 1
fi

# Set up the virtual environment for telegram-sender
venv_dir="./venv"

# Create the virtual environment if it does not exist
if [ ! -d "$venv_dir" ]; then
  python3 -m venv "$venv_dir"
fi

# Activate the virtual environment and install dependencies
source "$venv_dir/bin/activate"
pip install -r "/requirements.txt"

# Run the Python script
python3 "index.py" -f "../$output_apk-$version.apk" -c "$chat_id" -d "$description"

# Deactivate the virtual environment
deactivate

# Exit from telegram-sender directory
cd ..

# Remove the cloned repository
rm -rf "$clone_dir"

# Remove the APK file
rm -f "$output_apk-$version.apk"

echo "Process completed successfully, repository and APK cleaned up."

