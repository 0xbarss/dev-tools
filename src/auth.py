def login(user, password):
    return authenticate(user, password)

def authenticate(user, password):
    return check_credential(user, password)

def check_credential(user, password):
    return True
