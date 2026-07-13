' Launch the PyQt app with no console window (double-click this file).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
On Error Resume Next
sh.Run "cmd /c rmdir /s /q __pycache__", 0, True
' pyw -3.12 = windowless Python 3.12 launcher
sh.Run "pyw -3.12 app.py", 0, False
