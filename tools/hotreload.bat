@echo off

set params=%1
:loop
    shift
    if [%1]==[] goto afterloop
    set params=%params% %1
    goto loop
:afterloop

py "C:\Users\root\Desktop\sjps-python\tools\hotreload.py" %params%
