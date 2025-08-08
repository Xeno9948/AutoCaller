-- This AppleScript activates the 3CX Desktop App and dials a phone number.
-- It is designed to be called from a shell script with the number as an argument.

on run argv
	if (count of argv) is 0 then
		return "Error: No phone number was provided to the AppleScript."
	end if

	set theNumber to item 1 of argv
	log "Attempting to dial number: " & theNumber

	-- Check if the application is running
	if application "3CX Desktop App" is running then
		log "3CX Desktop App is running."
	else
		log "3CX Desktop App is not running, will try to launch."
	end if

	try
		tell application "3CX Desktop App"
			-- Bring the application to the front
			activate

			-- Give the app a moment to respond and become the frontmost application
			delay 1

			-- Use the 'open location' command to handle the tel: URL
			open location "tel:" & theNumber

			return "Successfully sent dial command for " & theNumber & " to 3CX Desktop App."
		end tell
	on error errMsg number errNum
		set error_message to "AppleScript Error: " & errMsg & " (Error Number: " & errNum & ")"
		log error_message

		if errNum is -1728 then
			return "Error: Could not find the application '3CX Desktop App'. Is it installed in the /Applications folder?"
		else
			return error_message
		end if
	end try
end run
