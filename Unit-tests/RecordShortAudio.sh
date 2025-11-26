#!/bin/bash

# Configuration
DURATION=5
FILENAME="recording_$(date +%Y%m%d_%H%M%S).wav"

# 1. Start recording in the background
# -f cd: CD quality (16 bit, 44.1kHz)
# -d $DURATION: Stop after duration
# > /dev/null 2>&1: Hide system output from arecord so it doesn't mess up the countdown
arecord -f cd -d "$DURATION" "$FILENAME" 1> /dev/null 2>&1 &

# Capture the Process ID (PID) of the recording just in case we need it
REC_PID=$!

# 2. Display Countdown
echo "MAKE! SOME! NOISE!!!!!!!!"
echo "Recording started. Saving to: $FILENAME"

for (( i=$DURATION; i>0; i-- )); do
    # printf allows us to update the same line using \r (carriage return)
    printf "Time remaining: %02d seconds... \r" "$i"
    sleep 1
done

# 3. Cleanup
# Wait for the background recording process to finish naturally
wait $REC_PID

# Print a new line to clear the carriage return line
echo -e "you should hear yourself back now:"

~
aplay $FILENAME
