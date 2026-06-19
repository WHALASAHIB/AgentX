"""Enable automated trading in MT5 terminal by modifying config."""
import os
import re

# MT5 terminal config path
USER = os.path.expanduser("~")
BASE = os.path.join(USER, "AppData", "Roaming", "MetaQuotes", "Terminal")

# Find the instance folder
instance_dirs = []
if os.path.isdir(BASE):
    for d in os.listdir(BASE):
        dd = os.path.join(BASE, d)
        if os.path.isdir(dd) and d != "Common" and d != "Community":
            instance_dirs.append(dd)

print(f"Found {len(instance_dirs)} MT5 instance(s)")

for inst in instance_dirs:
    config_file = os.path.join(inst, "config", "terminal.ini")
    if not os.path.isfile(config_file):
        print(f"  No terminal.ini in {inst}")
        continue
    
    print(f"  Reading: {config_file}")
    with open(config_file, "rb") as f:
        raw = f.read()
    
    text = raw.decode("utf-16-le", errors="replace")
    
    # Check if [ExpertAdvisors] section exists
    if "[ExpertAdvisors]" in text:
        print("  [ExpertAdvisors] section found")
        # Check current value
        for line in text.split("\n"):
            if "AutoTrading" in line:
                print(f"  Current: {line.strip()}")
    else:
        print("  No [ExpertAdvisors] section - adding it")
        # Add the section
        text += "\r\n[ExpertAdvisors]\r\n"
        text += "AutoTrading=1\r\n"
        
        # Write back as UTF-16 LE
        with open(config_file, "wb") as f:
            f.write(text.encode("utf-16-le"))
        print("  Added AutoTrading=1")
    
    # Also check for Common section settings
    common_file = os.path.join(inst, "config", "common.ini")
    if os.path.isfile(common_file):
        with open(common_file, "rb") as f:
            common_raw = f.read()
        common_text = common_raw.decode("utf-16-le", errors="replace")
        if "[Common]" in common_text:
            # Check if AutoTrading is in Common section
            if "AutoTrading" in common_text:
                for line in common_text.split("\n"):
                    if "AutoTrading" in line:
                        print(f"  Common.ini: {line.strip()}")
            else:
                print("  Adding AutoTrading to Common.ini")
                common_text += "\r\nAutoTrading=1\r\n"
                with open(common_file, "wb") as f:
                    f.write(common_text.encode("utf-16-le"))

print("\nDone. Restart MT5 terminal for changes to take effect.")
