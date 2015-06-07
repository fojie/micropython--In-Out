"""Test speed of SPI port for different baudrates and data and show when slow"""

from pyb import SPI, Pin, delay, micros, elapsed_micros, rng, disable_irq


def print_elapsed_time(baud, start_time, bursts, nr_bytes):
	time = elapsed_micros(start_time)
	t_p_burst = time / bursts
	nb = ''
	if bursts > 1 and t_p_burst > 500:  # Set to discrimanate between nnormal and "slow" transfers
		nb = 'SLOW !'
	print("%6s %7.3f Mbaud  Tot_time:%7.3f s %6.1f us between calls" % (nb, baud / 1e6, time / 1e6, t_p_burst))


baud_rates = [328125, 656250, 1312500, 2625000, 5250000, 10500000, 21000000]

spi = SPI(2, SPI.MASTER, baud_rates[0])
'''Since MISO is not connected, disable SPI for MISO by setting Pin as normal Pin input'''
miso_dummy = Pin('Y7', Pin.IN)  # May help prevent OS error 5 ?

""" Test SPI with data similar to graphical TFT traffic; Slow for some baudrates (10.5 Mbits/s) """
print("\nGraphical type data (2048 bursts of 4 bytes):")
for baud in baud_rates:
	spi.init(SPI.MASTER, baud)  # Change baud rate
	start = micros()

	for a in range(128):
		for x in range(16):
			spi.send(bytearray([0, x, 0, a]))
	print_elapsed_time(baud, start, 2048, 4)

""" Test SPI with generic data in ONE long buffer; Always(?) fast! """
print("\nGeneric data (8192 bytes pre-prepared as ONE long buffer):")
for baud in baud_rates:
	spi.init(SPI.MASTER, baud)  # Change baud rate
	data = bytearray([0, rng() & 0xFF, 0, rng() & 0xFF] * 2048)
	start = micros()
	spi.send(data)
	print_elapsed_time(baud, start, 1, 8192)

""" Test SPI with generic data; Slow for some baudrate and data sizes """
for nr_bytes in range(1, 17):
	data = [0] * nr_bytes
	bursts = 8192 // nr_bytes
	print("\nGeneric data (%1d bursts with %2d bytes)" % (bursts, nr_bytes))
	for baud in baud_rates:
		spi.init(SPI.MASTER, baud)  # Change baud rate
		start = micros()
		for _ in range(bursts):
			spi.send(bytearray(data))
		print_elapsed_time(baud, start, bursts, nr_bytes)
print()
