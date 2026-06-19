# WPSD-SeenGreat-UPS-Monitor
Script for Raspberry PI UPS from SeenGreat, to monitor and shut the pi down when battery falls below 20%


~~This script at this time is specifically written for the WPSD hotspot usage as it will write the the status to the OLED screen on the hotspot when the system is detected as running on battery.~~
The script is now fully updated to work with both Pi-Star and WPSD for the latest versions of both.  

It does require the Python3-smbus module which the installer script will attempt to install if it's not already installed.

To get started I forked the repository from seengreat here:  https://github.com/seengreat/Pi-Zero-UPS-USB-HUB

Specific to Pi-Star the steps for install would be:

SSH to the pi-star system and run the following

```bash
rpi-rw
git clone --branch Beta --single-branch -depth 1 https://github.com/TheSystech/WPSD-SeenGreat-UPS-Monitor.git
cd WPSD-SeenGreat-UPS-Monitor
chmod +x install.sh
sudo ./install.sh
rpi-ro

For wpsd it's a bit simpler because it doesn't do read-only file systems.
```bash
git clone --branch Beta --single-branch -depth 1 https://github.com/TheSystech/WPSD-SeenGreat-UPS-Monitor.git
cd WPSD-SeenGreat-UPS-Monitor
chmod +x install.sh
sudo ./install.sh

