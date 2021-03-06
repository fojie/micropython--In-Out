"""Functions for scanning keypad, debouncing and decoding pressed keys.

Uses a callback for timer 4 @50–100 Hz and in-line assembler for the scan function

2015-06-07 by Folke Berglund """

import stm
from pyb import Pin, delay, micros, elapsed_micros, Timer
from Lib_fifo import FIFO
# import array

"""# Globals for communication with timer callback routine
key_last    = 0
key_old     = 0
key_flag    = 0
key_buf     = array.array('i', [0]*25)      # Room for 20 key presses/releases"""

# Constants
NONE        = 0             # No key pressed
NEW         = 3             # key_flag = 3 means it's debounced and New
USED        = 4             # key_flag = 4 means consumer has received symbol (Not New anymore)
DEL_CNT     = const(100)    # Delay when scanning before reading (≈4 µs)


def port_init():
	""" Setup and Init Pins used in scan_keys; GPIOC used. """

	# Rows (Pull-ups inverted logic)
	pin0 = Pin("C0", Pin.IN, Pin.PULL_UP)       # C0–C3 inputs for reading 4 rows from keypad (inverted logic)
	pin1 = Pin("C1", Pin.IN, Pin.PULL_UP)
	pin2 = Pin("C2", Pin.IN, Pin.PULL_UP)
	pin3 = Pin("C3", Pin.IN, Pin.PULL_UP)

	# Columns (One column active (low) at the time) Open drain allows threading (OR-function without diodes)
	pin4 = Pin("C4", Pin.OUT_OD, Pin.PULL_UP)   # C4–C6 outputs for driving columns low one at the time
	pin5 = Pin("C5", Pin.OUT_OD, Pin.PULL_UP)
	pin6 = Pin("C6", Pin.OUT_OD, Pin.PULL_UP)
	pin7 = Pin("C7", Pin.OUT_PP)                # C7 used for timimg/debug: set low while scanning

	pin4.high()
	pin5.high()
	pin6.high()
	pin7.high()


@micropython.asm_thumb
def scan_keys():
	""" Scan All 3 columns for pressed/released keys.

	Calling function takes ≈ 5 / 17 µs when [no key] / [key pressed]
	Register usage;
		r7 -> GPIOC base
		r6 = mask for GPIO_C7 used as indicator (low while scanning)
		r5 = 8 used for shifts lsl
		r3 = mask for key readout bits
	At exit:
		r0 = key data for col0/col1/col2 MSB//LSB
			4 of 8 bits each used for rowNr (1(toprow), 2, 4 or 8) for pressed key(s)
	"""
	# r7 -> GPIOC base address
	movwt(r7, stm.GPIOC)            # r7 -> Base of PortC
	# First check if ANY key pressed
	mov(r1, 0b01110000 + 0b10000000) # All columns + C7 as indicator
	strh(r1, [r7, stm.GPIO_BSRRH])  # (Re)set ALL Columns + C7 low (active)

	# Short delay; do some house keeping before reading
	# Prepare for inverting and masking col- and key-bits
	mov(r6, 0b10000000)             # Prepare for setting C7 high at exit
	mov(r5, 8)                      # r5 = nr shifts for lsl
	mov(r4, 0b01111111)
	mov(r3, 0b1111)                 # Mask for key readout bits

	ldrb(r0, [r7, stm.GPIO_IDR])    # Read 8 bits from input to r0
	eor(r0, r4)
	and_(r0, r3)                    # Keep only key bits
	beq(EXIT_NO_KEY)                # No key pressed, exit with r0 = 0

	mov(r1, 0b01100000)
	strh(r1, [r7, stm.GPIO_BSRRL])  # Set two Columns high and keep C4 low

	# delay for a while (≈4 µs)
	movwt(r2, DEL_CNT)
	label(delay_0)
	sub(r2, r2, 1)
	bne(delay_0)

	ldrb(r0, [r7, stm.GPIO_IDR])    # Read 8 bits from col0 keys to r0
	eor(r0, r4)
	and_(r0, r3)                    # Keep only key bits
	lsl(r0, r5)                     # Make room for next col

	mov(r1, 0b01010000)
	strh(r1, [r7, stm.GPIO_BSRRL])  # Set two Columns high
	mov(r1, 0b00100000)
	strh(r1, [r7, stm.GPIO_BSRRH])  # (Re)set col1 C5 low (active)

	# delay for a while (≈4 µs)
	movwt(r2, DEL_CNT)
	label(delay_1)
	sub(r2, r2, 1)
	bne(delay_1)

	ldrb(r1, [r7, stm.GPIO_IDR])    # Read 8 bits from col1 keys to r1
	eor(r1, r4)
	and_(r1, r3)                    # Keep only key bits
	orr(r0, r1)                     # Add data to previous col
	lsl(r0, r5)                     # Make room for next col

	mov(r2, 0b00110000)
	strh(r2, [r7, stm.GPIO_BSRRL])  # Set two Columns high
	mov(r2, 0b01000000)
	strh(r2, [r7, stm.GPIO_BSRRH])  # (Re)set col2 C6 low (active)

	# delay for a while (≈4 µs)
	movwt(r2, DEL_CNT)
	label(delay_2)
	sub(r2, r2, 1)
	bne(delay_2)

	ldrb(r2, [r7, stm.GPIO_IDR])    # Read 8 bits from col2 keys to r2
	eor(r2, r4)
	and_(r2, r3)                    # Keep only key bits
	orr(r0, r2)                     # Add data to previous cols
	''' r0 now contains all 3 key-data; col0 as MSB and col2 as LSB '''
	label(EXIT_NO_KEY)
	strh(r6, [r7, stm.GPIO_BSRRL])  # Set C7 high to signal End-of-scan


#################################
#
#   Callback for keypad scanner
#
@micropython.native
def scan_timer_callback(timer):  # Called @50–100 Hz by Timer
	"""Callback for Timer. Scan keypad and debounce. Takes 13 / 26 µs [no key] / [key pressed].
	Returns key(s) in key_buf (FIFO)
		key_debounce: key_flag:
			0 : key changed (pressed or released)
			1 : 1:st debounce cycle
			2 : 2:nd debounce cycle
			3 : Valid (still pressed) = NEW (export)
			4 : Acknowledged (set to USED by consumer) and not considered new anymore
	"""

	global key_last, key_old, key_flag, key_buf

	key_last = scan_keys()      # Call Assembler routine
	if key_last == key_old:
		if key_flag == 2:       # EXPORT key
			fifo.put(key_buf, key_last)
			key_flag = NEW      # = 3 One loop more so we don't come back here (When Consumer clears key_flag)
		elif key_flag < 2:
			key_flag += 1       # One loop more
		else:
			pass                # Do nothing: Wait until keys change
	else:
		key_flag = NONE         # = 0 New key or key released
		key_old = key_last      # Key changed!: wait till next scans and check if stable


@micropython.native
def key_to_symbol(key):
	""" Translate key to key_symbol(s).

	Return string: active key's symbols; empty if no key pressed """

	# Dictionary with lookUp tables for key-code to character
	# Can handle up to 2 chrs in same column (per column)
	#
	# Connected to PortC as  inputs: C0 – C3 to row 0 – 3 ('123'  to '*0#')  pull-up
	#                       outputs: C4 – C6 to col 0 – 2 ('147*' to '369#') pull-up, open drain, active low
	#
	COL0 = {1: '1', 2: '4', 3: '14', 4: '7', 5: '17', 6: '47', 8: '*', 9: '*1', 10: '*4', 12: '*7'}
	COL1 = {1: '2', 2: '5', 3: '25', 4: '8', 5: '28', 6: '58', 8: '0', 9: '20', 10: '50', 12: '80'}
	COL2 = {1: '3', 2: '6', 3: '36', 4: '9', 5: '39', 6: '69', 8: '#', 9: '3#', 10: '6#', 12: '9#'}

	def _2_symbol(rc, c_dict):
		_list = []
		for k, v in c_dict.items():
			if k == rc:
				_list.append(v)
		if _list:                       # If more than 2 keys pressed in same col: _list = []
			_st = _list.pop()
		else:
			_st = ''
		return _st

	''' Decode key to symbol(s) '''
	if not key:
		return ''                       # No key pressed: return ''
	else:
		symb = []
		rc0 = key >> 16                 # Get key from col0
		if rc0:
			l0 = _2_symbol(key >> 16, COL0)     # Get key from col0
			symb.append(l0)
		rc1 = (key >> 8) & 0xF
		if rc1:
			l1 = _2_symbol(rc1, COL1)
			symb.append(l1)
		rc2 = key & 0xF
		if rc2:
			l2 = _2_symbol(rc2, COL2)
			symb.append(l2)
	return "".join(symb)


if __name__ == '__main__':

	port_init()                         # Init PortC for keypad

	# Todo: why do we sometimes get: 'scan_keys()' not defined? in the callback when Timer 4 or 5 is used ?
	''' scan_keys: ['9', '9'] 521
		uncaught exception in Timer(4) interrupt handler
		NameError: name 'scan_keys' is not defined
		scan_keys: ['7', '', '9', '5', '6', ''] 1285
		Traceback (most recent call last):
		  File "test_keypad.py", line 48, in <module>
	'''
	tim = Timer(5, freq=50)             # create a timer object using timer 5 - trigger at 50Hz
	tim.callback(scan_timer_callback)   # set the callback to keypad-scanner

	fifo = FIFO(key_buf)                # FIFO-object with global buffer

	while True:
		""" Since the consumer probably is slower than scan_keys, short key presses will be missed.
		Debouncing is done in the callback as well as setting key_flag (status).

		Decoding is done here in the consumer """

		if key_flag == NEW:  # CONSUMER
			symbol = []
			if fifo.nr_unfetched(key_buf):
				start = micros()
				data = fifo.get_all(key_buf)
				for i in data:
					symbol.append(key_to_symbol(i))
				key_flag = USED         # Acknowledge as taken
				delta = elapsed_micros(start)
			print("scan_keys:", symbol, delta)

			if '#' in symbol:
				break
		delay(200)

	tim.callback(None)                  # Stop callback
	print()
