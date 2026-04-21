def add(x, y):
    """Return the sum of x and y."""
    return x + y

def multiply(x, y):
    """Return the product of x and y."""
    return x * y

if __name__ == "__main__":
    result = multiply(add(2, 2), 5)
    print(result)