
import os
from getpass import getpass
from werkzeug.security import generate_password_hash, check_password_hash

contrasena = getpass("Crea una contraseña nueva: ")
hash_generado = generate_password_hash(contrasena)

verificacion = getpass("Escribe la misma contraseña otra vez: ")

if check_password_hash(hash_generado, verificacion):
    with open("admin_hash.txt", "w", encoding="utf-8") as archivo:
        archivo.write(hash_generado)

    print("¡Contraseña verificada!")
    print("Hash guardado correctamente en admin_hash.txt")
else:
    print("Las contraseñas no coinciden. Ejecuta el programa otra vez.")
