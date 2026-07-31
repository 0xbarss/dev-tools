# sample_repo — collected source

- Files: 3
- Total tokens (approx.): 57
- Total size: 305 bytes

## `tests/test_auth.py`

```python
def test_login():
    assert True
```

## `src/auth.py`

```python
def login(user, password):
    return authenticate(user, password)

def authenticate(user, password):
    return check_credential(user, password)

def check_credential(user, password):
    return True
```

## `src/main.py`

```python
def main():
    print('hello')

if __name__ == '__main__':
    main()
```
