# MicroPython
Mostly for pyboard

*test_SPI.py* is a test program, that checks the speed of SPI for different burst sizes at all Baudrates.
*Lib_keypad* is a scanner for keypad (0–9, * and #) using Timer 4 in a callback with debouncing and export. The callback also calls an inline assembler routine for fast low level scanning.
*Lib_keypad.py* contains methods for scanning a keypad, debouncing and decoding. It uses a timer's callback and calls a i-line assembler function, and export data via a FIFO. See *Lib_fifo.py*.