def format_feature(text):
    return text.upper()

def get_greeting():
    return format_feature('hello ')

def main():
    print(get_greeting())

if __name__ == "__main__":
    main()