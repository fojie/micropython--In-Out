__author__ = 'folke'

from pyb import UART, delay, micros, elapsed_micros, Pin
import binascii


class HA7S:
	""" Class for 1-wire master using HA7S.

	Contains drivers for:
		DS18B20 temp sensor
		Display controller PIC for LCD
		DS2423 Counter (2 channels 32 bits counters)
	"""

	def __init__(self, uart_port):
		self.ROW_LENGTH = 20  # LCD 4 rows x 20 chars
		self.uart = UART(uart_port, 9600)

	def scan_for_devices(self):
		""" Find all 1-Wire rom_codes on the bus """
		strt = micros()
		rom_codes = []  # Prepare list with Units found on the bus
		r = ""  # Return string

		r = self.tx_rx('S', 17)  # Search for first device
		if len(r) > 1:
			rom_codes.append(r[:-1])  # Add to list (Skip final <cr>)
		##print("Första enhet: ", rom_codes)

		while True:
			# delay(100)
			r = self.tx_rx('s', 17)  # Search next rom_codes todo: ger timeout sista gången
			if len(r) > 1:
				rom_codes.append(r[:-1])  # Add to list (Skip final <cr>)
			else:
				break
		# print("Enheter: ", rom_codes)
		##print("Scan for devices: ", elapsed_micros(strt) / 1e6, 's')
		return rom_codes

	def read_ds18b20_temp(self, rom):
		""" Setup and read temp data from DS18b20 """

		# Todo: check negative temps works
		retries = 3
		while retries:
			""" Initiate Temperature Conversion by selecting and sending 0x44-command """
			resp = self.tx_rx(b'A' + rom + '\r', 17)  # Adressing
			dummy = self.tx_rx('W0144\r', 3)  # Write block of data '44' Trigg measurement
			resp1 = self.tx_rx('M\r', 17)  # Reset AND reselect (enl HA7S doc)
			if resp1 == resp:
				delay(750)  # Give DS18B20 time to measure
				# The temperature result is stored in the scratchpad memory
				data = self.tx_rx(b'W0ABEFFFFFFFFFFFFFFFFFF\r', 21)  # Write to scratchpad and READ result
				dummy = self.tx_rx('R', 1)  # Reset
				m = self.hex_byte_to_int(data[4:6])
				l = self.hex_byte_to_int(data[2:4])
				t = (m << 8) | (l & 0xff)
				if m < 8:
					t *= 0.0625  # Convert to Temp [°C]; Plus
				else:
					# temp given as 2's compl 16 bit int
					t = (t - 65536) * 0.0625  # Convert to Temp [°C]; Minus
				print("Rom, retur temperatur: ", rom, data, t, '°C')
				return t
			else:
				retries -= 1
				print("Retries: resp, resp1: ", retries, resp, resp1)
				if retries < 1:
					break

	def read_ds2423_counters(self, rom):
		""" Read counter values for the two counters (A & B) conncted to external pins """

		resp = self.tx_rx(b'A' + rom + '\r', 17)  # Adressing

		""" Write/read block: A5 01C0/01E0(CounterA/B) [MSByte sent last] + 'FF'*42 (timeslots during which slave
		returns	32 bytes scratchpad data + 4(cntA/cntB) + 4(zeroBytes) + 2 CRC bytes """

		# Todo: check if respons = written; repeat otherwise
		# We set adr so we only read LAST byte of page 14. We also get counter(4 B) + zerobytes(4 B) and CRC(2 B)
		dataA = self.tx_rx('W0EA5DF01' + 'FF' * 11 + '\r', 29)  # Read mem & Counter + TA1/TA2 (adr = 0x11C0)
		dummy = self.tx_rx('M\r', 17)  # Reset AND reselect (enl HA7S doc)

		# We set adr so we only read LAST byte of page 15. We also get counter(4 B) + zerobytes(4 B) and CRC(2 B)
		dataB = self.tx_rx('W0EA5FF01' + 'FF' * 11 + '\r', 29)  # Read mem & Counter + TA1/TA2 (adr = 0x11C0)
		dummy = self.tx_rx('R\r', 1)  # Reset and red data (b'BE66014B467FFF0A102D\r')

		''' Convert 32 bits hexadecimal ascii-string (LSByte first) to integer '''
		cntA = self.lsb_first_hex_ascii_to_int32(dataA[8:16])
		cntB = self.lsb_first_hex_ascii_to_int32(dataB[8:16])

		print("ReadCnt: ", cntA, cntB, dataA, dataB)
		return (cntA, cntB)

	def write_ds2423_scratchpad(self, rom, s, target_adr):
		""" Write to Scratchpad (max 32 bytes)

		target_adr [0..0x1FF] as integer

		Not implemented: readback of CRC after end of write. This works ONLY if data
		written extends to end of page """

		self.tx_rx(b'A' + rom + '\r', 17)  # Adressing

		""" Write to scratach: 'OF' [TA1/TA2] (Byte reversed) + data string as hex ascii
		HA7S can only write 32 bytes in a chunk. """

		# Todo: check if respons = written; repeat otherwise
		# Check string length AND that it fits on page (check target_adr + s_len)
		s_len = len(s)
		if target_adr < 0x200 and s_len <= 32 and (target_adr % 0x20) + s_len <= 32:
			swap_adr = self.int8_to_2hex_string(target_adr & 0xFF) + self.int8_to_2hex_string(target_adr >> 8)
			if s_len > 29:
				''' Send first 16 bytes only, as first part '''
				resp1 = self.tx_rx('W130F' + swap_adr + self.bin2hex(s[:16]) + '\r', 7 + 32)  # First 16 bytes of data
				''' Adjust parameters for next write '''
				nr_bytes_hex = self.int8_to_2hex_string(s_len - 16)
				s = s[16:]
				s_len -= 16
				# Send rest of string as second part
				resp2 = self.tx_rx('W' + nr_bytes_hex + self.bin2hex(s) + '\r', 1 + (s_len * 2))  # Only string now
				resp = resp1[:6] + ':' + resp1[6:-1] + '/' + resp2
			else:
				nr_bytes_hex = self.int8_to_2hex_string(3 + s_len)
				resp = self.tx_rx('W' + nr_bytes_hex + '0F' + swap_adr + self.bin2hex(s) + '\r', 7 + (s_len * 2))
			dummy = self.tx_rx('R\r', 1)  # Reset and stop

			print("write_ds2423_scratchpad: Reponse", resp)
		else:
			print("write_ds2423_scratchpad: String will not fit!; Target_adr or length of string to big!")

	def read_and_copy_ds2423_scratchpad(self, rom):
		""" Read Scratchpad and copy to SRAM

		First TA1/TA2 and 'Ending offset E/S' is fetched from scratchpad contents and then
		the offset inside scratchpad is set to 5 lsbits of TA1, and data is fetched from there until 'Ending offset'.
		'Ending offset' is the offset for the last chr written to scratchpad

		Finally a copy of (updated part of) scratchpad is written to SRAM """

		# Todo: check if respons = written; repeat otherwise
		self.tx_rx(b'A' + rom + '\r', 17)  # Adressing

		auth = self.tx_rx('W04AA' + ('FF' * 3) + '\r', 9)  # Read 'AA' + TA1/TA2 + Status(E/S)
		target_adr = (self.hex_byte_to_int(auth[4:6]) << 8) + self.hex_byte_to_int(auth[2:4])  # MSB and LSB Swapped
		status = self.hex_byte_to_int(auth[6:8])
		print(" read_and_copy_ds2423_scratchpad: auth, targetAdress, Status(E/S) 'Ending offset': ",
		      auth, hex(target_adr), hex(status & 0x1F))

		''' Continue reading timeslots until end of written part of scratchpad '''
		nr_bytes = (status & 0x1F) - (target_adr & 0x1F) + 1  # 1+Ending offset-Start offset = # bytes written/to read
		nr_bytes_hex = self.int8_to_2hex_string(nr_bytes)
		data = self.tx_rx('W' + nr_bytes_hex + ('FF' * nr_bytes) + '\r', (2 * nr_bytes) + 1)  # Read rest of chars

		dummy = self.tx_rx('M\r', 17)  # Reset and adress again

		""" Write Copy scratchpad command: copy scratchpad to memory –– Authenticate with previous TA1/TA2 + E/S """
		a = list(auth[2:-1])
		s = ''
		for b in a:
			s += chr(b)
		##print("auth: ", a, chr(b), s)

		resp = self.tx_rx('W045A' + s + '\r', 9)  # Copy Scratch: '5A' + TA1/TA2 + Status(E/S)
		dummy = self.tx_rx('R\r', 1)  # Reset and stop

		print(" read_and_copy_ds2423_scratchpad: Repons: ", resp[:-1], ':', data, nr_bytes)
		return data

	def read_ds2423_mem(self, rom, page):
		""" Read Memory page (32 bytes)

		page = page-number as integer [0..15]; the whole page is read.
		If reading includes the last byte in a page, DS2423 also sends counter value(4 bytes) + 12 bytes more
		Reading can continue into next page, BUT HA7S can only read 32 bytes in a chunk. """

		# Todo: check if respons = written; repeat otherwise
		page_adr = self.int16_to_4hex_string((page % 16) * 0x20)
		page_swap = page_adr[2:] + page_adr[:2]  # Swap MSB and LSB

		resp = self.tx_rx(b'A' + rom + '\r', 17)  # Adressing

		""" Write/read block: A5 01C0/01E0(CounterA/B) [or ANY PAGE (= adr)] + 'FF'*42 (timeslots during which slave
		returns	32 ramData + 4(cntA/cntB) + 2(0) + 2 CRC bytes; All data as hex ascii (Byte reversed) """
		data1 = self.tx_rx('W13F0' + page_swap + 'FF' * 16 + '\r', 39)  # Read mem + TA1/TA2 (adr = 0x01E0)
		''' We can continue sending timeslots for reading data until we send Reset '''
		data2 = self.tx_rx('W10' + 'FF' * 16 + '\r', 33)  # Continue fetching ram data

		dummy = self.tx_rx('R\r', 1)  # Reset and stop reading

		##print("Repons: ", resp, data1, data2)

		d = data1[6:-1] + data2[:-1]  # Skip respons, cmd, TA1, TA2 and '\r'
		s = self.hex_bytes_to_str(d)
		return (d, s)

	def lcd_init(self, rom, use_custom_chars=True):
		""" Init LCD with custom chr generator """

		if use_custom_chars:
			# Load Character generator into user area of CG-RAM
			# chr0 = [0b10001, 0b01111]
			chr0 = [0b01010, 0b00000, 0b00100, 0b01010, 0b11111, 0b10001, 0b10001, 0b00000,  # 'Ä' {'ä' finns i #225}
			        0b01010, 0b00000, 0b01110, 0b10001, 0b10001, 0b10001, 0b01110, 0b00000,  # 'Ö' {'ö' finns i #239}
			        0b00100, 0b01010, 0b00100, 0b01110, 0b10001, 0b11111, 0b10001, 0b00000,  # 'Å'
			        0b00100, 0b01010, 0b00100, 0b01110, 0b10001, 0b10001, 0b01111, 0b00000,  # 'å'
			        0b01100, 0b10010, 0b10010, 0b01100, 0b00000, 0b00000, 0b00000, 0b00000,  # '°'
			        0b00000, 0b00000, 0b01111, 0b10001, 0b10001, 0b01111, 0b00001, 0b01110,  # 'g'
			        0b01010, 0b00000, 0b01110, 0b00001, 0b01110, 0b10001, 0b01111, 0b00000,  # 'ä' finns i #225
			        0b00000, 0b01010, 0b00000, 0b01110, 0b10001, 0b10001, 0b01110, 0b00000]  # 'ö' finns i #239

			''' First adress PIC via HA7Scommand "A" '''
			dummy = self.tx_rx(b'A' + rom + b'\r', 17)  # Adressing
			dummy = self.tx_rx('W021040\r', 5)  # Write 0x40 directly to LCD register: Set start adr = 0 in CG-RAM
			delay(1)
			dummy = self.tx_rx('M\r', 17)               # Reset AND reselect

			for c in chr0:  # Send chr0 to LCD CG-RAM (max 8 chrs á 8 bytes)
				dummy = self.tx_rx('W0212' + self.bin2hex(chr(c)) + '\r', 5)  # Write font (chr0) to LCD CG-RAM
				delay(1)
				dummy = self.tx_rx('M\r', 17)           # Reset AND reselect

			# Switch back to pointing to DDRAM (NOT CGRAM), else will clobber CGRAM !!
			# self.hal_write_command(0x80 | 0)          # Set start adr = 0
			dummy = self.tx_rx('W021080\r', 5)  # Write 0x40 directly to LCD register memory: Point to CDDRAM
			delay(1)
			dummy = self.tx_rx('R\r', 17)               # Reset

	def print_on_lcd(self, rom, msg, row_nr, col=0, clear_LCD=False, use_custom_chars=False):
		""" Send text message to scratchpad memory in PIC with HA7S Write/Read block cmd
		then copy from scratchpad to LCD

		N.B. swedish char åäöÅÄÖ and other non US-ASCII charas are sent as UTF-8 (2 chars)
		entries in user_char with chr >127, does not work? """

		user_char = {'Ä': chr(0), 'Ö': chr(1), 'Å': chr(2), 'å': chr(3),  # Custom chr in CGRAM
		             '°': chr(4), 'g': chr(5),  # Custom chr in CGRAM
		             'ä': chr(225), 'ö': chr(239), 'p': chr(240),  # Already available in CGROM
		             '∑': chr(246), 'Ω': chr(244), 'µ': chr(228)}  # todo: investigeate if works if > 127

		# Row nr to LCD memory adr for start of row [0–3]   [Valid for 4 rows x 20 chars LCD ONLY]
		lcd_row_adr = {0: 0x00, 1: 0x40, 2: 0x14, 3: 0x54}

		''' First adress LCD kontroller via HA7Scommand "A" '''
		dummy = self.tx_rx(b'A' + rom + b'\r', 17)  # Adressing

		if clear_LCD:
			''' Clear display first '''
			delay(1)
			dummy = self.tx_rx('W0149\r', 3)    # Write block '49' 1 byte: Clear LCD
			delay(3)
			dummy = self.tx_rx('M\r', 17)       # Reset AND reselect

		line_adr = self.bin2hex(chr(lcd_row_adr[row_nr] + col))  # LCD memory adr to use on LCD for chosen row

		''' Convert msg to string of hex bytes
		Truncate msg if msg longer than fits on row (20 chars)'''
		if use_custom_chars:
			s = ''
			for char in msg:                    # Exchange some chars
				if char in user_char:           # character should be changed?
					s += user_char[char]        # change char if so
				else:
					s += char
			msg = s

		msg_len = len(msg)
		if msg_len > (self.ROW_LENGTH - col):
			msg_len = self.ROW_LENGTH - col
			msg_hex = self.bin2hex(msg[:self.ROW_LENGTH - col])  # Truncate
		else:
			msg_hex = self.bin2hex(msg)         # Convert to hex string (no '0x' before each byte)

		''' Can only transfer max 16 chars to scratchpad LCD memory per transfer: First tfr 16 chrs + 2nd tfr for rest '''
		if msg_len > 16:
			len_hex = self.bin2hex(chr(16 + 2))  # Limit to 16 + 2 bytes first transmission
			dummy = self.tx_rx('W' + len_hex + '4E' + line_adr + msg_hex[:16 * 2] + '\r', 37)  # Write first 16 chars to
			# scratchpad
			delay(1)
			dummy = self.tx_rx('M\r', 17)       # Reset AND reselect
			dummy = self.tx_rx('W0148\r', 3)    # Copy Scratchpad to LCD
			''' Adjust parameters for next part of msg to write to LCD memory '''
			msg_len -= 16
			msg_hex = msg_hex[16 * 2:]          # keep unsent part only
			line_adr = self.bin2hex(chr(lcd_row_adr[row_nr] + col + 16))  # LCD memory adr to use on LCD for 17:th
			# char
			dummy = self.tx_rx('M\r', 17)       # Reset AND reselect (enl HA7S doc)

		len_hex = self.bin2hex(chr(msg_len + 2))  # Len = BYTE count for remaining data
		dummy = self.tx_rx('W' + len_hex + '4E' + line_adr + msg_hex + '\r', len(msg_hex) + 5)  # Write to scratchpad
		delay(1)
		resp1 = self.tx_rx('M\r', 17)           # Reset AND reselect
		dummy = self.tx_rx('W0148\r', 3)        # Copy Scratchpad to LCD
		delay(2)
		''' Turn LCD back-light ON '''
		dummy = self.tx_rx('M\r', 17)           # Reset AND reselect
		dummy = self.tx_rx('W0108\r', 3)        # Write block '08' 1 byte: LCD backlight on
		dummy = self.tx_rx('R', 1)              # Reset

	def tx_rx(self, tx, nr_chars):
		""" Send command to and receive respons from SA7S"""
		''' rx = uart.readall() # Receive respons TAKES 1.0 sec ALWAYS (after uart.any) TimeOut!!!! '''
		i = 0
		rx = ''
		# todo: do check if respons == same as sent: repeat otherwise
		self.uart.write(tx)  # Send to unit
		# print("uart.write: i, tx: ", i,  tx[:-1])
		while True:  # Typiskt 2–3 (search: 4) varv i loopen
			i += 1
			if self.uart.any():  # returns True if any characters wait
				dbg.high()
				strt = micros()
				rx = b''
				j = 0
				while True:  # Typically 10–20 (search: 12; M, R & W0144: 1) loops
					j += 1
					rxb = self.uart.read(nr_chars)  # uart.readln och uart.readall ger båda timeout (1s default)
					rx = rx + rxb
					if (len(rx) >= nr_chars) or (rxb == b'\r'):  # End of search returns \r
						break
				dbg.low()
				##print("uart.read: i, j, tx, rx, ∆time ", i, j, tx[:-1], rx, len(rx), elapsed_micros(strt) / 1e6, 's')
				delay(84)
				break
			else:
				delay(10)
		return rx

	def hex_bytes_to_str(self, s):
		""" Convert bytes (2 ascii hex char each) to string of ascii chars """

		def hex_char_to_int(c):
			##print("c:", hex(c), chr(c))
			if c >= 65:
				c -= 55  # 'A' = 10
			else:
				c -= 48  # '0' = 0
			return c

		r = ''
		s = str.upper(s)  # Raise to upper case

		for i in range(0, len(s), 2):
			m = hex_char_to_int(s[i])
			l = hex_char_to_int(s[i + 1])
			t = (m << 4) + (l & 0xf)
			r += chr(t)
		##print("Byte: r", r)
		return r

	def hex_byte_to_int(self, s):
		""" Convert byte (2 ascii hex char) to int """

		def hex_char_to_int(c):
			##print("c:", hex(c), chr(c))
			if c >= 65:
				c -= 55  # 'A' = 10
			else:
				c -= 48  # '0' = 0
			return c

		r = []
		s = str.upper(s)  # Raise to upper case

		for i in range(0, len(s), 2):
			m = hex_char_to_int(s[i])
			l = hex_char_to_int(s[i + 1])
			t = (m << 4) + (l & 0xf)
			r.append(t)
		##print("Byte: m l t r", m, l, t, r)
		return r[0]

	def lsb_first_hex_ascii_to_int32(self, s):
		""" Convert 32 bits hexadecimal ascii-string (LSByte first) to 32 bit integer """
		cnt = (self.hex_byte_to_int(s[6:8]) << 24) + (self.hex_byte_to_int(s[4:6]) << 16) + \
		      (self.hex_byte_to_int(s[2:4]) << 8) + self.hex_byte_to_int(s[0:2])
		return cnt

	def bin2hex(self, s):  # Works for i 0–127; NOT 128+
		""" Convert integer to hex string with full width w/o '0x'-prefix """
		return binascii.hexlify(s).decode("utf-8")

	def int4_to_1hex_string(self, i4):
		""" Convert integer to hex string with full width w/o '0x'-prefix """
		return ''.join('{:01X}'.format(i4))

	def int8_to_2hex_string(self, i8):
		""" Convert integer to hex string with full width w/o '0x'-prefix """
		return ''.join('{:02X}'.format(i8))

	def int16_to_4hex_string(self, i16):
		""" Convert integer to hex string with full width w/o '0x'-prefix """
		return ''.join('{:04X}'.format(i16))

	def int32_to_8hex_string(self, i32):
		""" Convert integer to hex string with full width w/o '0x'-prefix """
		return ''.join('{:08X}'.format(i32))

####################################################################
#
#   Main
#
if __name__ == "__main__":
	dbg = Pin("X9", Pin.OUT_PP)  # Debug pin
	dbg.low()

	print("\nSöker efter alla enheter på 1wire-bussen…")

	one_w = HA7S(4)  # Create & init 1wire master on uart port #4

	""" Discover all Devices """
	rom_codes = one_w.scan_for_devices()
	# rom_codes = [b'220000067C406C28', b'620000067C267528', b'FE041469A283FF28', b'67030100000000FC', b'F60000000CDFAD1D', b'68000100000903FF']

	print("Enheter: ", rom_codes)

	cntr_rom = b'F60000000CDFAD1D'  # DS2423 counter ROM code
	lcd_rom = b'68000100000903FF'
	count = one_w.read_ds2423_counters(cntr_rom)
	print("Counter A, B: ", count)

	"""# Fill all SRAM with <spc> chr
	for page in range(0, 16):
		one_w.write_ds2423_scratchpad(cntr_rom, ' ' * 32, page * 0x20)
		one_w.read_and_copy_ds2423_scratchpad(cntr_rom)

	for page in range(0, 16):
		page_data = one_w.read_ds2423_mem(cntr_rom, page)
		print("Page ", page, " memory: ", page_data[0], page_data[1])
		b = bytearray(page_data[0])
	"""
	use_custom_chars = False
	"""one_w.lcd_init(lcd_rom, use_custom_chars)
	if use_custom_chars:
		one_w.print_on_lcd(lcd_rom, "Hej åäöÅÄÖ 13°C ∑µ", 0, clear_LCD=True)
	else:
		one_w.print_on_lcd(lcd_rom, "Temperaturer", 0, clear_LCD=True)"""

	""" For all DS18B02: read temp and display """
	i = 0
	for u in rom_codes:
		if u[-2:] == b'28':  # Family = DS18B20
			temp = one_w.read_ds18b20_temp(u)  # Read temp from one DS18B20
			msg = "Temp: " + str(temp) + '°C'
			# print(msg)
			strt = micros()
			##one_w.print_on_lcd(lcd_rom, msg, i+1)
			i += 1
		##print("DeltaT: ", elapsed_micros(strt) / 1e6)

print()
