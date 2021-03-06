""" Test of Lib_keypad """

from Lib_keypad import port_init, scan_timer_callback, scan_keys, key_to_symbol
from pyb import Timer, delay, micros, elapsed_micros
from Lib_fifo import FIFO
import array


# Globals for communication with timer callback routine
key_last = 0
key_old = 0
key_flag = 0
key_buf = array.array('i', [0] * 25)  # Room for 20 key presses/releases

# Constants
NONE = 0  # No key pressed
NEW = 3  # key_flag = 3 means it's debounced and New
USED = 4  # key_flag = 4 means consumer has received symbol (Not New anymore)

if __name__ == '__main__':

	port_init()  # Init PortC for keypad

	tim = Timer(5, freq=100)            # create a timer object using timer 5 - trigger at 50Hz
	tim.callback(scan_timer_callback)   # set the callback to keypad-scanner

	# Todo: why do we sometimes get: 'scan_keys()' not defined? in the callback when Timer 4 or 5 is used ?
	''' scan_keys: ['9', '9'] 521
		uncaught exception in Timer(4) interrupt handler
		NameError: name 'scan_keys' is not defined
		scan_keys: ['7', '', '9', '5', '6', ''] 1285
		Traceback (most recent call last):
		  File "test_keypad.py", line 48, in <module>
	'''

	fifo = FIFO(key_buf)  # FIFO-object with global buffer

	while True:
		""" Since the consumer probably is slower than scan_keys, short key presses will be missed.
		Debouncing is done in the callback as well as setting key_flag (status).

		Decoding is done here in the consumer """

		if key_flag == NEW:  # CONSUMER
			symbol = []
			if fifo.nr_unfetched(key_buf):  # Unfetched data available ?
				start = micros()
				data = fifo.get_all(key_buf)  # Get all as a tuple
				for d in data:
					symbol.append(key_to_symbol(d))
				key_flag = USED  # Acknowledge as taken
				delta = elapsed_micros(start)
			print("scan_keys:", symbol, delta)

			if '#' in symbol:
				break
		delay(200)

	tim.callback(None)  # Stop callback
	print()
