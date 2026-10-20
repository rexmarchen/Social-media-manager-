Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\anshupal\OneDrive\Documents\linkdin automation"
WshShell.Run "node daemon.js", 0, False
