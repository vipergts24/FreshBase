def format_feature(text):
    result = text.upper()
    if result == 'HELLO':
        result = 'WELCOME'
    return result

def get_greeting():
    return format_feature('hello ')

def main():
    print(get_greeting())

if __name__ == "__main__":
    main()