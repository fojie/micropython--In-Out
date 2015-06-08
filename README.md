# MicroPython
Mostly for pyboard

*test_SPI.py* is a test program, that checks the speed of SPI for different burst sizes at all Baudrates.

Folder *Keypad* with *Lib_fifo.py* and *Lib_keypad.py* contains methods for scanning a keypad, debouncing and decoding. It uses a timer's callback, calls a in-line assembler function, and export data via a FIFO. Together they implement a scanner for keypad (0–9, * and #) using a Timer in a callback with debouncing and export. The callback also calls an inline assembler routine for really fast low level scanning.

Folder *1wire* contains *Lib_HA7S.py* which is a class that handles the 1-wire as a Master with the help of the HA7S unit. It's handy since it releives the user of (some of) the low end programming. It can also drive the 1-wire bus better and protects the micro controller. Threre are drivers for the well known temperature sensor DS18B20 and the counter DS2423 as well as a Display interface Pic, that contains firmware for common LCD displays, such as the 4 x 20 chrs implemented here. The library is still under development, but should be functional. Missing are CRC checking and retries in case of data errors (that happens occasionally).
