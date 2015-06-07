"""Methods for circular buffer of type FIFO. callable from callbacks."""
__author__ = 'folke'

from pyb import enable_irq, disable_irq
import array


class FIFO:
	"""Methods implementing a FIFO using array.array with 8 / 16 / 32-bits data.

	Callable with the following types of arrays:
		array.array('i', [n,…])     # For 32-bits   signed data
		array.array('I', [n,…])     # For 32-bits Unsigned data
		array.array('h', [n,…])     # For 16-bits   signed data
		array.array('H', [n,…])     # For 16-bits Unsigned data
		array.array('b', [n,…])     # For 8-bits    signed data      Max length = 255
		array.array('B', [n,…])     # For 8-bits  Unsigned data      Max length = 255
	Length of array must be 5 more than needed for data; Min length = 7
		"""

	def __init__(self, arr):
		"""
		arr is setup so that:
			Word 0: peek        copy of last put data (updated even if FIFO full)
			Word 1: put_ptr     where to put next data (index)
			Word 2: get_ptr     where to get next data (index)
			Word 3: nr_data     Nr of data in FIFO
			Word 4: tot_sz      allocated total size (=len(arr), incl Word0 – Word4)
			Word 5+: data

		All pointers are index (0 – size-1)
		"""
		size = len(arr)
		if size < 7:
			print("Buffer too small; Must be 5 more than necessary for data!")
		else:
			arr[0] = -1  # Set peek (copy of last put data)
			arr[1] = 5  # Set put_ptr
			arr[2] = 5  # Set get_ptr
			arr[3] = 0  # Set nr_data
			arr[4] = size  # = len(arr)

	def nr_unfetched(self, arr):
		return arr[3]

	def room_left(self, arr):
		return arr[4] - arr[3] - 5

	def flush(self, arr):
		arr[1] = 5  # Set put_ptr
		arr[2] = 5  # Set get_ptr
		arr[3] = 0  # Set nr_data

	def put(self, arr, data):  # Todo: What if data is a tuple or list? Add method put_all ?
		""" Put new data into buffer and increase nr_bytes.

		Skips new data if buffer already full, but "peek" is always updated
		"""
		arr[0] = data  # Always update peek = last input data
		s = arr[3]  # nr_data = already in arr
		if s < arr[4] - 5:  # Check if room for more
			p = arr[1]  # Yes, so Fetch put_ptr
			arr[p] = data
			p += 1
			if p >= arr[4]:
				p = 5                   # Make circular (skipping pointers in beginning)
			arr[1] = p  # Update put_ptr -> next position to put data
			''' Protect the critical section: update nr_data (do not use 's' since it could be old)'''
			int_stat = disable_irq()    # We don't want an interrupt just now
			arr[3] += 1  # Publish new data
			enable_irq(int_stat)        # Restore previous mask
		else:
			pass                        # We are full, do nothing

	def get(self, arr):
		""" Get new data from buffer and decrease nr_bytes.

		If no data available, return -1 (MaxInt when Uint)
		"""
		if arr[3]:  # nr_data available
			p = arr[2]  # OK, Fetch get_ptr
			data = arr[p]
			p += 1
			if p >= arr[4]:
				p = 5                   # Make circular
			arr[2] = p  # Update get_ptr -> next position to get data from
			''' Protect the critical section: update nr_data '''
			int_stat = disable_irq()    # We don't want an interrupt just now
			arr[3] -= 1  # Publish new data
			enable_irq(int_stat)        # Restore previus mask
		else:
			data = -1                   # Oops: no data available !
		return data

	def get_all(self, arr):
		l = []
		for i in range(arr[3]):
			l.append(self.get(arr))
		return tuple(l)


if __name__ == "__main__":
	""" Test with 3 datasizes signed/unsigned """
	i = array.array('i', [0] * 12)
	I = array.array('I', [0] * 12)

	fifo = FIFO(i)
	fifo.put(i, 32767)
	fifo.put(i, 32768)
	fifo.put(i, 65535)
	fifo.put(i, -1)
	print(i)
	fifo = FIFO(I)
	fifo.put(I, 32767)
	fifo.put(I, 32768)
	fifo.put(I, 65535)
	fifo.put(I, -1)
	print(I)

	h = array.array('h', [0] * 12)
	H = array.array('H', [0] * 12)

	fifo = FIFO(h)
	fifo.put(h, 32767)
	fifo.put(h, 32768)
	fifo.put(h, 65535)
	fifo.put(h, -1)
	print(h)
	fifo = FIFO(H)
	fifo.put(H, 32767)
	fifo.put(H, 32768)
	fifo.put(H, 65535)
	fifo.put(H, -1)
	print(H)

	b = array.array('b', [0] * 12)
	B = array.array('B', [0] * 12)

	fifo = FIFO(b)
	fifo.put(b, 127)
	fifo.put(b, 128)
	fifo.put(b, 255)
	fifo.put(b, -1)
	print(b)
	fifo = FIFO(B)
	fifo.put(B, 127)
	fifo.put(B, 128)
	fifo.put(B, 255)
	fifo.put(B, -1)
	print(B)

	print()
