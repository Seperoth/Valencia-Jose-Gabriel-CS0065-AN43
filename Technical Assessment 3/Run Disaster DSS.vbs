Option Explicit
Dim shell, fso, folder
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
On Error Resume Next
shell.Run "pythonw.exe """ & folder & "\main.py""", 0, False
If Err.Number <> 0 Then
    MsgBox "Could not start Disaster DSS. Install Python 3.10 or later. To see startup errors, open a terminal in this folder and run: python main.py", 48, "Disaster DSS"
End If
