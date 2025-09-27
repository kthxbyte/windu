# Windu Project

Disk usage display for your Windows cmd.exe or powershell console.

This project is also a quick vibe coding exercise using [gemini-cli](https://cloud.google.com/gemini/docs/codeassist/gemini-cli) to create a full python-based project from scratch. 100% of the program code and most of this README file has been generated automatically.


## Setup

1. **Create and activate a virtual environment:**
   ```sh
   py -m venv venv
   .\venv\Scripts\activate
   ```

2. **Install the required dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

### Dependency Note

This project uses `windows-curses`, a library specific to the Windows operating system, as a replacement for the standard `curses` module found on Unix-like systems.
