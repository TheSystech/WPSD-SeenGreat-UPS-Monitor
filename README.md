# WPSD-SeenGreatUPS-Monitor
Script for Raspberry PI UPS from SeenGreat, to monitor and shut the pi down when battery falls below 20%

This script at this time is specifically written for the WPSD hotspot usage as it will write the the status to the OLED screen on the hotspot when the system is detected as running on battery.

For this script to work it also requires the INA219.py script from seengreat's github, locate here: https://github.com/seengreat/Pi-Zero-UPS-USB-HUB

You'll want to copy in the INA219.py script into the directory where you cloned this script to.

You can either manually follow the steps in install.sh, or you can chmod +x on install.sh and run it with SUDO after cloning to the system.
