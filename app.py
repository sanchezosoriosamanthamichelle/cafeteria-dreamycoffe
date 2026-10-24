import os
from flask import (
    Flask, render_template, request, redirect,
    url_for, abort, session, flash
)
from functools import wraps
from werkzeug.security import check_password_hash
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime
from flask import jsonify
import uuid
from werkzeug.utils import secure_filename


app = Flask(__name__)
mongo_uri = os.environ.get("MONGO_URI")
if not mongo_uri:
    if os.environ.get("RENDER"):
        raise RuntimeError("Configura MONGO_URI en Render.")
    mongo_uri = "mongodb://127.0.0.1:27017/"

cliente = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
base_datos = cliente["dreamy_coffe"]
alumnos = base_datos["productos"]
pedidos = base_datos["pedidos"]
    
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("Configura la variable FLASK_SECRET_KEY.")


def administrador_requerido(funcion):
    @wraps(funcion)
    def verificar_sesion(*args, **kwargs):
        if not session.get("administrador"):
            flash("Inicia sesión para acceder al panel.", "warning")
            return redirect(url_for("login"))
        return funcion(*args, **kwargs)
    return verificar_sesion


@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if session.get("administrador"):
        return redirect(url_for("panel_admin"))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        contrasena = request.form.get("contrasena", "")

        usuario_correcto = os.environ.get("ADMIN_USERNAME", "")
        hash_correcto = os.environ.get("ADMIN_PASSWORD_HASH", "")
        

        if (
            usuario_correcto
            and hash_correcto
            and usuario == usuario_correcto
            and check_password_hash(hash_correcto, contrasena)
        ):
            session["administrador"] = True
            return redirect(url_for("panel_admin"))

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("admin_login.html")



@app.route("/admin")
@administrador_requerido
def panel_admin():
    lista = list(alumnos.find().sort("nombre", 1))
    lista_pedidos = list(
        pedidos.find().sort("fecha", -1)
    )

    return render_template(
        "admin.html",
        alumnos=lista,
        pedidos=lista_pedidos
    )


@app.route("/admin/pedido/<numero_pedido>/marcar-pagado", methods=["POST"])
@administrador_requerido
def marcar_pedido_pagado(numero_pedido):
    resultado = pedidos.update_one(
        {
            "numero_pedido": numero_pedido,
            "estado_pago": "Pendiente"
        },
        {
            "$set": {
                "estado_pago": "Pagado"
            }
        }
    )

    if resultado.modified_count == 1:
        flash(
            f"El pedido {numero_pedido} se marcó como pagado.",
            "success"
        )
    else:
        pedido = pedidos.find_one({
            "numero_pedido": numero_pedido
        })

        if pedido is None:
            flash("No se encontró el pedido.", "danger")
        else:
            flash(
                "El pedido no está pendiente de pago o ya fue pagado.",
                "warning"
            )

    return redirect(url_for("panel_admin"))


@app.route("/admin/logout", methods=["POST"])
@administrador_requerido
def logout():
    session.clear()
    flash("Has cerrado sesión.", "success")
    return redirect(url_for("login"))



def leer_formulario(datos=None):
    if datos is None:
        datos = request.form

    campos = ("nombre", "categoria", "estado", "precio", "descripcion")

    if any(not isinstance(datos.get(c, ""), str) for c in campos):
        abort(400, description="Los campos deben contener texto.")

    nombre = datos.get("nombre", "").strip()
    categoria = datos.get("categoria", "").strip()
    estado = datos.get("estado", "").strip()
    descripcion = datos.get("descripcion", "").strip()
    precio_texto = datos.get("precio", "").strip()

    if not nombre or not categoria or not estado or not precio_texto:
        abort(400, description="Completa nombre, categoría, precio y estado.")

    if len(nombre) > 80 or len(categoria) > 20:
        abort(400, description="Máximo: nombre 80 y categoría 20.")

    if len(descripcion) > 300:
        abort(400, description="La descripción no puede superar 300 caracteres.")

    if estado not in ["Disponible", "Agotado"]:
        abort(400, description="Selecciona un estado válido.")

    try:
        precio = float(precio_texto)
    except ValueError:
        abort(400, description="El precio debe ser un número válido.")

    if precio < 0 or precio > 100000:
        abort(400, description="El precio debe estar entre 0 y 100000.")

    return {
    "nombre": nombre,
    "categoria": categoria,
    "precio": precio,
    "descripcion": descripcion,
    "estado": estado,
    "imagen": "producto-default.jpg"
    }

def buscar_alumno(id):
    if not ObjectId.is_valid(id):
        abort(404, description="La clave del producto no es válida.")
    alumno = alumnos.find_one({"_id": ObjectId(id)})
    if alumno is None:
        abort(404, description="Este producto ya no existe.")
    return alumno


@app.route("/")
def inicio():
    termino = request.args.get("buscar", "").strip()

    filtro = {}

    if termino:
        filtro["$or"] = [
            {"nombre": {"$regex": termino, "$options": "i"}},
            {"categoria": {"$regex": termino, "$options": "i"}},
            {"descripcion": {"$regex": termino, "$options": "i"}}
        ]

    lista = list(alumnos.find(filtro).sort("nombre", 1))

    return render_template(
        "index.html",
        alumnos=lista,
        buscar=termino
    )



@app.route("/agregar", methods=["POST"])
@administrador_requerido
def agregar():
    datos = leer_formulario()

    archivo = request.files.get("imagen")

    if archivo and archivo.filename:
        nombre_seguro = secure_filename(archivo.filename)
        extension = os.path.splitext(nombre_seguro)[1].lower()

        extensiones_permitidas = {".jpg", ".jpeg", ".png", ".webp"}

        if not nombre_seguro or extension not in extensiones_permitidas:
            abort(400, description="Selecciona una imagen JPG, PNG o WEBP.")

        nombre_imagen = f"{uuid.uuid4().hex}{extension}"

        carpeta_imagenes = os.path.join(
            app.root_path, "static", "img"
        )
        os.makedirs(carpeta_imagenes, exist_ok=True)

        ruta_imagen = os.path.join(carpeta_imagenes, nombre_imagen)
        archivo.save(ruta_imagen)

        datos["imagen"] = nombre_imagen

    resultado = alumnos.insert_one(datos)

    print("ID DEL PRODUCTO GUARDADO:", resultado.inserted_id)

    return redirect(url_for("inicio"))


@app.route("/editar/<id>", methods=["GET", "POST"])
@administrador_requerido
def editar(id):
    alumno = buscar_alumno(id)

    if request.method == "POST":
        datos = leer_formulario()

        # Conservar la imagen actual si no se selecciona otra
        datos["imagen"] = alumno.get(
            "imagen", "producto-default.jpg"
        )

        archivo = request.files.get("imagen")

        if archivo and archivo.filename:
            nombre_seguro = secure_filename(archivo.filename)
            extension = os.path.splitext(nombre_seguro)[1].lower()

            extensiones_permitidas = {
                ".jpg", ".jpeg", ".png", ".webp"
            }

            if (
                not nombre_seguro
                or extension not in extensiones_permitidas
            ):
                abort(
                    400,
                    description="Selecciona una imagen JPG, PNG o WEBP."
                )

            nombre_imagen = f"{uuid.uuid4().hex}{extension}"

            carpeta_imagenes = os.path.join(
                app.root_path, "static", "img"
            )
            os.makedirs(carpeta_imagenes, exist_ok=True)

            ruta_imagen = os.path.join(
                carpeta_imagenes, nombre_imagen
            )
            archivo.save(ruta_imagen)

            datos["imagen"] = nombre_imagen

        alumnos.update_one(
            {"_id": alumno["_id"]},
            {"$set": datos}
        )

        return redirect(url_for("inicio"))

    return render_template("editar.html", alumno=alumno)


@app.route("/eliminar/<id>", methods=["POST"])
@administrador_requerido
def eliminar(id):
    alumno = buscar_alumno(id)
    alumnos.delete_one({"_id": alumno["_id"]})
    return redirect(url_for("inicio"))

@app.errorhandler(PyMongoError)
def error_mongo(error):
    mensaje = "No fue posible conectar con la base de datos."
    if request.path.startswith("/api/"):
        return jsonify({"error": mensaje}), 503
    return render_template("error.html", mensaje=mensaje), 503

@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
def error_peticion(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), error.code
    return render_template(
        "error.html", mensaje=error.description
    ), error.code

@app.route("/ayuda")
def ayuda():
    fecha = datetime.now().strftime("%d/%m/%Y")
    return render_template("ayuda.html", fecha=fecha)

def producto_json (producto):
    return {
        "id": str(producto ["_id"]),
        "nombre": producto ["nombre"],
        "categoria": producto ["categoria"],
        "estado": producto ["estado"]
        }
def leer_json():
    datos = request.get_json(silent=True)
    if not isinstance (datos, dict):
        abort (400, description="Envía un objeto JSON válido.")
    return leer_formulario(datos)


@app.route("/menu")
def menu():
    lista = list(alumnos.find().sort("nombre", 1))
    return render_template("menu.html", alumnos=lista)


@app.context_processor
def datos_carrito():
    carrito = session.get("carrito", {})
    cantidad = sum(int(c) for c in carrito.values())
    return {"cantidad_carrito": cantidad}


@app.route("/carrito")
def ver_carrito():
    carrito = session.get("carrito", {})
    productos_carrito = []
    total = 0

    for producto_id, cantidad in carrito.items():
        producto = alumnos.find_one({"_id": ObjectId(producto_id)})

        if producto:
            precio = float(producto.get("precio", 0))
            subtotal = precio * int(cantidad)
            productos_carrito.append({
                "id": producto_id,
                "nombre": producto.get("nombre", "Producto"),
                "precio": precio,
                "cantidad": int(cantidad),
                "subtotal": subtotal
            })
            total += subtotal

    return render_template(
        "carrito.html",
        productos=productos_carrito,
        total=total
    )


@app.route("/carrito/agregar/<producto_id>", methods=["POST"])
def agregar_carrito(producto_id):
    if not ObjectId.is_valid(producto_id):
        abort(404)

    producto = alumnos.find_one({"_id": ObjectId(producto_id)})

    if not producto:
        abort(404)

    if producto.get("estado") != "Disponible":
        flash("Este producto no está disponible.")
        return redirect(request.referrer or url_for("menu"))

    carrito = session.get("carrito", {})
    cantidad_actual = int(carrito.get(producto_id, 0))
    carrito[producto_id] = cantidad_actual + 1
    session["carrito"] = carrito

    flash(f"{producto.get('nombre', 'Producto')} se agregó al carrito.")
    return redirect(request.referrer or url_for("menu"))


@app.route("/carrito/actualizar/<producto_id>", methods=["POST"])
def actualizar_carrito(producto_id):
    if not ObjectId.is_valid(producto_id):
        abort(404)

    try:
        cantidad = int(request.form.get("cantidad", "1"))
    except ValueError:
        abort(400, description="Cantidad no válida.")

    if cantidad < 1 or cantidad > 99:
        abort(400, description="La cantidad debe estar entre 1 y 99.")

    carrito = session.get("carrito", {})

    if producto_id in carrito:
        carrito[producto_id] = cantidad
        session["carrito"] = carrito

    return redirect(url_for("ver_carrito"))


@app.route("/carrito/eliminar/<producto_id>", methods=["POST"])
def eliminar_carrito(producto_id):
    carrito = session.get("carrito", {})
    carrito.pop(producto_id, None)
    session["carrito"] = carrito
    return redirect(url_for("ver_carrito"))



@app.route("/finalizar-compra", methods=["GET", "POST"])
def finalizar_compra():
    carrito = session.get("carrito", {})
    productos_carrito = []
    total = 0

    # Obtener los productos disponibles del carrito
    for producto_id, cantidad in carrito.items():
        if not ObjectId.is_valid(producto_id):
            continue

        producto = alumnos.find_one({
            "_id": ObjectId(producto_id)
        })

        if not producto or producto.get("estado") != "Disponible":
            continue

        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            abort(400, description="Cantidad no válida.")

        if cantidad < 1 or cantidad > 99:
            abort(400, description="Cantidad no válida.")

        precio = float(producto.get("precio", 0))
        subtotal = round(precio * cantidad, 2)

        productos_carrito.append({
            "producto_id": producto_id,
            "nombre": producto.get("nombre", "Producto"),
            "precio": precio,
            "cantidad": cantidad,
            "subtotal": subtotal
        })

        total += subtotal

    total = round(total, 2)

    if not productos_carrito:
        flash("Tu carrito está vacío o no tiene productos disponibles.")
        return redirect(url_for("ver_carrito"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        telefono = request.form.get("telefono", "").strip()
        metodo_pago = request.form.get("metodo_pago", "").strip()
        entrega = request.form.get("entrega", "").strip()

        if not nombre or not telefono:
            flash("Completa tu nombre y teléfono.", "warning")

        elif len(nombre) > 100 or len(telefono) > 20:
            abort(400, description="Revisa los datos ingresados.")

        elif metodo_pago not in ("recoger", "tarjeta"):
            flash("Selecciona una forma de pago válida.", "warning")
            
        elif entrega not in ("recoger", "consumir"):
            flash("Selecciona cómo deseas recibir tu pedido.", "warning")
        else:
            estado_pago = "Pendiente"
            nombre_metodo_pago = "Pago al recoger"

            if metodo_pago == "tarjeta":
                import re
                numero_tarjeta = re.sub(
                    r"[\s-]",
                    "",
                    request.form.get("tarjeta_numero", "")
                )

                vencimiento = request.form.get(
                    "tarjeta_vencimiento", ""
                ).strip()

                cvv = request.form.get(
                    "tarjeta_cvv", ""
                ).strip()

                tarjeta_valida = (
                    numero_tarjeta.isdigit()
                    and len(numero_tarjeta) == 16
                    and re.fullmatch(
                        r"(0[1-9]|1[0-2])/[0-9]{2}",
                        vencimiento
                    ) is not None
                    and re.fullmatch(r"[0-9]{3,4}", cvv) is not None
                )

                if tarjeta_valida:
                    mes_txt, anio_txt = vencimiento.split("/")
                    mes = int(mes_txt)
                    anio = 2000 + int(anio_txt)

                    ahora = datetime.now()

                    if (anio, mes) < (ahora.year, ahora.month):
                        tarjeta_valida = False

                if not tarjeta_valida:
                    flash(
                        "Los datos de prueba de la tarjeta no son "
                        "válidos. Usa únicamente datos ficticios.",
                        "warning"
                    )

                    return render_template(
                        "finalizar_compra.html",
                        productos=productos_carrito,
                        total=total,
                        confirmado=False
                    )

                # Pago ficticio: no se realiza ningún cobro.
                estado_pago = "Pagado (simulación)"
                nombre_metodo_pago = "Tarjeta (simulación)"

            # Crear el pedido sin guardar datos de la tarjeta
            numero_pedido = uuid.uuid4().hex[:12].upper()

            nuevo_pedido = {
                "numero_pedido": numero_pedido,
                "cliente": {
                    "nombre": nombre,
                    "telefono": telefono
                },
                "productos": productos_carrito,
                "total": total,
                "entrega": (
                    "Recoger en cafetería"
                    if entrega == "recoger"
                    else "Consumir en cafetería"
                    ),
                "metodo_pago": nombre_metodo_pago,
                "estado_pago": estado_pago,
                "estado_pedido": "Recibido",
                "estado": "Pendiente",
                "fecha": datetime.now()
            }

            pedidos.insert_one(nuevo_pedido)
            session["carrito"] = {}

            return render_template(
                "finalizar_compra.html",
                confirmado=True,
                pedido=nuevo_pedido,
                productos=[],
                total=total
            )

    return render_template(
        "finalizar_compra.html",
        productos=productos_carrito,
        total=total,
        confirmado=False
    )
@app.route("/api/productos", methods=["GET", "POST"])
def api_productos():
    if request.method == "POST":
        if not session.get("administrador"):
            abort(401, description="Debes iniciar sesión como administrador.")
        datos = leer_json()
        resultado= alumnos.insert_one(datos)
        producto= buscar_alumno (str(resultado.inserted_id))
        return jsonify(producto_json (producto)), 201
    lista =alumnos.find().sort("nombre", 1)
    return jsonify([producto_json(p) for p in lista])

@app.route("/api/productos/<id>", methods=["GET", "PUT", "DELETE"])
def api_producto (id):
    producto = buscar_alumno(id)
    if request.method == "PUT":
        if not session.get("administrador"):
            abort(401, description="Debes iniciar sesión como administrador.")
        datos = leer_json()
        alumnos.update_one({"_id": producto ["_id"] }, { "$set": datos})
        return jsonify(producto_json (buscar_alumno(id)))
    if request.method == "DELETE":
        if not session.get("administrador"):
            abort(401, description="Debes iniciar sesión como administrador.")
        alumnos.delete_one({"_id": producto ["_id"]})
        return "", 204
    return jsonify (producto_json(producto))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
