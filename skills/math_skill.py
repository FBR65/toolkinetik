"""Math skill — example skill for the Agno Agent OS."""


def calculate_fibonacci(n: int) -> int:
    """Berechnet die n-te Fibonacci-Zahl.
    Args:
        n (int): Die Position in der Fibonacci-Folge.
    """
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b