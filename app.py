import os
from flask import ( Flask, render_template, request, redirect,url_for, abort, session, flash)
from functools import wraps
from werkzeug.security import check_password_hash
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import PyMongoError, DuplicateKeyError
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from datetime import date
from zoneinfo import ZoneInfo
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
reservaciones = base_datos["reservaciones"]
bloqueos_reservas = base_datos["bloqueos_reservas"]

# CONFIGURACIÓN DE RESERVACIONES

MESAS = [
    {"numero": 1, "ubicacion": "Interior"},
    {"numero": 2, "ubicacion": "Interior"},
    {"numero": 3, "ubicacion": "Interior"},
    {"numero": 4, "ubicacion": "Exterior"},
    {"numero": 5, "ubicacion": "Exterior"},
    {"numero": 6, "ubicacion": "Exterior"}
]

HORARIOS_RESERVA = [
    {
        "inicio": "09:00",
        "fin": "11:00",
        "duracion": 120
    },
    {
        "inicio": "11:00",
        "fin": "13:00",
        "duracion": 120
    },
    {
        "inicio": "13:00",
        "fin": "15:00",
        "duracion": 120
    },
    {
        "inicio": "15:00",
        "fin": "17:00",
        "duracion": 120
    },
    {
        "inicio": "17:00",
        "fin": "19:00",
        "duracion": 120
    },
    {
        "inicio": "19:00",
        "fin": "20:00",
        "duracion": 60
    }
]

TIEMPO_APARTADO = 60

ZONA_HORARIA = ZoneInfo("America/Cancun")

def hora_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def hora_cancun():
    return datetime.now(ZONA_HORARIA)

HORA_APERTURA = "09:00"
HORA_CIERRE = "20:00"

    
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

def buscar_mesa_disponible(mesa_numero, fecha_hora, fecha_final, ahora):

    # Comprobar que la mesa exista
    mesa = next(
        (m for m in MESAS if m["numero"] == mesa_numero),
        None
    )

    if mesa is None:
        return None

    # Buscar reservaciones que coincidan con la mesa
    reservacion_existente = reservaciones.find_one({
        "mesa": mesa_numero,

        "fecha_hora": {"$lt": fecha_final},
        "fecha_final": {"$gt": fecha_hora},

        "$or": [
            {"estado": "Confirmada"},
            {
                "estado": "En espera",
                "expires_at": {"$gt": ahora}
            }
        ]
    })

    # Si ya está ocupada en ese horario
    if reservacion_existente:
        return None

    return mesa



def expirar_reservaciones():
    ahora = hora_utc()

    reservaciones.update_many(
        {
            "estado": "En espera",
            "expires_at": {"$lte": ahora}
        },
        {
            "$set": {
                "estado": "Expirada"
            }
        }
    )


def adquirir_bloqueo_reservas():
    propietario = uuid.uuid4().hex
    ahora = hora_utc()

    try:
        bloqueo = bloqueos_reservas.find_one_and_update(
            {
                "_id": "asignacion_mesas",
                "$or": [
                    {"hasta": {"$lte": ahora}},
                    {"hasta": {"$exists": False}}
                ]
            },
            {
                "$set": {
                    "propietario": propietario,
                    "hasta": ahora + timedelta(seconds=30)
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

    except DuplicateKeyError:
        return None

    if bloqueo and bloqueo.get("propietario") == propietario:
        return propietario

    return None


def liberar_bloqueo_reservas(propietario):
    if propietario:
        bloqueos_reservas.update_one(
            {
                "_id": "asignacion_mesas",
                "propietario": propietario
            },
            {
                "$set": {
                    "hasta": hora_utc()
                }
            }
        )


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
    expirar_reservaciones()

    lista = list(alumnos.find().sort("nombre", 1))

    lista_pedidos = list(
        pedidos.find().sort("fecha", -1)
    )

    # Mostrar únicamente reservaciones confirmadas
    lista_reservaciones = list(
        reservaciones.find(
            {"estado": "Confirmada"}
        ).sort("fecha_hora", 1)
    )

    return render_template(
        "admin.html",
        alumnos=lista,
        pedidos=lista_pedidos,
        reservaciones=lista_reservaciones
    )
@app.route("/admin/reservacion/<id>/cancelar", methods=["POST"])
@administrador_requerido
def cancelar_reservacion(id):

    if not ObjectId.is_valid(id):
        abort(404)

    ahora = hora_utc()

    resultado = reservaciones.update_one(
        {
            "_id": ObjectId(id),
            "estado": {"$in": ["Confirmada", "En espera"]}
        },
        {
            "$set": {
                "estado": "Cancelada",
                "fecha_cancelacion": ahora
            }
        }
    )

    if resultado.modified_count == 1:
        flash("La reservación fue cancelada.", "success")
    else:
        flash("No se encontró una reservación activa.", "warning")

    return redirect(url_for("panel_admin"))
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
def bienvenida():
    return render_template("bienvenida.html")


@app.route("/inicio")
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

@app.route("/reservar")
def reservar():

    return render_template(
    "reservar.html",
    fecha_minima=hora_cancun().date().isoformat(),
    mesas=MESAS,
    horarios=HORARIOS_RESERVA
    )

@app.route("/api/reservaciones", methods=["GET"])
def api_reservaciones():
    # Obtener la fecha solicitada
    fecha = request.args.get("fecha", "").strip()

    try:
        fecha_seleccionada = datetime.strptime(
            fecha,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        return jsonify({
            "ok": False,
            "mensaje": "La fecha no es válida."
        }), 400

    ahora = hora_utc()

    # Actualizar el estado de los apartados vencidos
    expirar_reservaciones()

    cliente_id = session.get("cliente_reservas_id")

    resultado_mesas = []

    # Recorrer las seis mesas
    for mesa in MESAS:

        horarios_mesa = []

        # Revisar cada horario de esa mesa
        for horario in HORARIOS_RESERVA:

            fecha_hora = datetime.strptime(
                f"{fecha} {horario['inicio']}",
                "%Y-%m-%d %H:%M"
            )

            fecha_final = datetime.strptime(
                f"{fecha} {horario['fin']}",
                "%Y-%m-%d %H:%M"
            )

            reservacion = reservaciones.find_one({
                "mesa": mesa["numero"],
                "fecha_hora": {"$lt": fecha_final},
                "fecha_final": {"$gt": fecha_hora},
                "$or": [
                    {"estado": "Confirmada"},
                    {
                        "estado": "En espera",
                        "expires_at": {"$gt": ahora}
                    }
                ]
            })

            # Estado inicial
            estado = "Disponible"

            datos_horario = {
                "inicio": horario["inicio"],
                "fin": horario["fin"],
                "estado": estado
            }

            if reservacion:

                if reservacion["estado"] == "Confirmada":

                    datos_horario["estado"] = "Reservada"

                elif reservacion["estado"] == "En espera":

                    segundos = max(
                        0,
                        int(
                            (
                                reservacion["expires_at"] - ahora
                            ).total_seconds()
                        )
                    )

                    datos_horario["estado"] = "En proceso"
                    datos_horario["id"] = str(reservacion["_id"])
                    datos_horario["segundos_restantes"] = segundos
                    datos_horario["expires_at"] = (
                        reservacion["expires_at"].isoformat() + "Z"
                    )
                    datos_horario["expires_at_timestamp"] = int(
                        reservacion["expires_at"].replace(
                            tzinfo=timezone.utc
                            ).timestamp() * 1000
                        )

                    datos_horario["es_mi_apartado"] = (
                        cliente_id is not None
                        and reservacion.get("cliente_id") == cliente_id
                    )

            horarios_mesa.append(datos_horario)

        resultado_mesas.append({
            "numero": mesa["numero"],
            "ubicacion": mesa["ubicacion"],
            "horarios": horarios_mesa
        })

    return jsonify({
        "ok": True,
        "fecha": fecha,
        "mesas": resultado_mesas
    })


@app.route("/crear-reservacion", methods=["POST"])
def crear_reservacion():

    # Detectar si la solicitud viene de la nueva tabla
    es_api = request.is_json

    if es_api:
        datos = request.get_json(silent=True) or {}
    else:
        datos = request.form

    nombre = datos.get("nombre", "").strip()
    telefono = datos.get("telefono", "").strip()
    fecha = datos.get("fecha", "").strip()
    mesa_numero = datos.get("mesa", "").strip()
    horario_inicio = datos.get("horario", "").strip()

    # Función para responder según el tipo de solicitud
    def respuesta_error(mensaje, codigo=400):
        if es_api:
            return jsonify({
                "ok": False,
                "mensaje": mensaje
            }), codigo

        flash(mensaje, "warning")
        return redirect(url_for("reservar"))

    # Validar campos obligatorios
    if not nombre or not telefono or not fecha or not mesa_numero or not horario_inicio:
        return respuesta_error("Completa todos los campos.")

    # Validar nombre y teléfono
    if len(nombre) > 100:
        return respuesta_error("El nombre es demasiado largo.")

    if not telefono.isdigit() or not 10 <= len(telefono) <= 15:
        return respuesta_error("Ingresa un teléfono válido.")

    # Validar número de mesa
    try:
        mesa_numero = int(mesa_numero)
    except ValueError:
        return respuesta_error("Selecciona una mesa válida.")

    mesa = next(
        (m for m in MESAS if m["numero"] == mesa_numero),
        None
    )

    if mesa is None:
        return respuesta_error("La mesa seleccionada no existe.")

    # Buscar el horario seleccionado
    horario = next(
        (
            h for h in HORARIOS_RESERVA
            if h["inicio"] == horario_inicio
        ),
        None
    )

    if horario is None:
        return respuesta_error("Selecciona un horario válido.")

    # Validar fecha
    try:
        fecha_hora = datetime.strptime(
            f"{fecha} {horario['inicio']}",
            "%Y-%m-%d %H:%M"
        )

        fecha_final = datetime.strptime(
            f"{fecha} {horario['fin']}",
            "%Y-%m-%d %H:%M"
        )

    except ValueError:
        return respuesta_error("La fecha seleccionada no es válida.")


    ahora = hora_cancun().replace(tzinfo=None)
    ahora_utc = hora_utc()
    
    if fecha_hora <= ahora:
        return respuesta_error("Selecciona un horario futuro.")

    # Identificar al cliente mediante su sesión
    if "cliente_reservas_id" not in session:
        session["cliente_reservas_id"] = uuid.uuid4().hex

    cliente_id = session["cliente_reservas_id"]

    # Limpiar reservaciones vencidas
    expirar_reservaciones()

    # Evitar asignaciones simultáneas
    propietario = adquirir_bloqueo_reservas()

    if not propietario:
        return respuesta_error(
            "Estamos procesando otra reservación. Intenta nuevamente.",
            409
        )

    try:
        mesa_disponible = buscar_mesa_disponible(
            mesa_numero,
            fecha_hora,
            fecha_final,
            ahora_utc
        )

        if mesa_disponible is None:
            return respuesta_error(
                "Esta mesa ya está reservada para el horario seleccionado.",
                409
            )

        nueva_reservacion = {
            "nombre": nombre,
            "telefono": telefono,
            "cliente_id": cliente_id,
            "fecha_hora": fecha_hora,
            "fecha_final": fecha_final,
            "duracion_minutos": horario["duracion"],
            "mesa": mesa_numero,
            "ubicacion": mesa["ubicacion"],
            "horario": horario_inicio,
            "estado": "En espera",
            "fecha_registro": ahora_utc,
            "expires_at": ahora_utc + timedelta(seconds=TIEMPO_APARTADO)
        }

        resultado = reservaciones.insert_one(nueva_reservacion)

        nueva_reservacion["_id"] = resultado.inserted_id

    finally:
        liberar_bloqueo_reservas(propietario)
        
        print("Bloqueo liberado para:", propietario)
        
        print(
            "Resultado de liberación:",
            bloqueos_reservas.find_one({"_id": "asignacion_mesas"})
            )

    # Respuesta para la nueva tabla
    if es_api:
        return jsonify({
            "ok": True,
            "mensaje": "Tu mesa está apartada temporalmente.",
            "id": str(nueva_reservacion["_id"]),
            "mesa": mesa_numero,
            "ubicacion": mesa["ubicacion"],
            "fecha": fecha,
            "horario": horario_inicio,
            "estado": "En espera",
            "expires_at": nueva_reservacion["expires_at"].isoformat() + "Z",
            "segundos_restantes": TIEMPO_APARTADO
        }), 201

    # Mantener el funcionamiento anterior de formularios tradicionales
    nueva_reservacion["folio"] = str(nueva_reservacion["_id"])

    return render_template(
        "confirmacion_reserva.html",
        reserva=nueva_reservacion,
        segundos_restantes=TIEMPO_APARTADO,
        temporal=True
    )




@app.route("/confirmar-reservacion/<id>", methods=["POST"])
def confirmar_reservacion(id):

    if not ObjectId.is_valid(id):
        abort(404)

    ahora = hora_utc()

    cliente_id = session.get("cliente_reservas_id")

    if not cliente_id:
        mensaje = "No tienes permiso para confirmar este apartado."

        if request.is_json:
            return jsonify({
                "ok": False,
                "mensaje": mensaje
            }), 403

        flash(mensaje, "warning")
        return redirect(url_for("reservar"))

    resultado = reservaciones.update_one(
        {
            "_id": ObjectId(id),
            "cliente_id": cliente_id,
            "estado": "En espera",
            "expires_at": {"$gt": ahora}
        },
        {
            "$set": {
                "estado": "Confirmada",
                "fecha_confirmacion": ahora
            },
            "$unset": {
                "expires_at": ""
            }
        }
    )

    if resultado.modified_count == 1:

        reserva = reservaciones.find_one({
            "_id": ObjectId(id)
        })

        if reserva is None:
            abort(404)

        reserva["folio"] = str(reserva["_id"])

        if request.is_json:
            return jsonify({
                "ok": True,
                "mensaje": "¡Tu reservación ha sido confirmada!",
                "url_recibo": url_for(
                    "ver_recibo_reservacion",
                    id=id
                )
            }), 200


        return render_template(
            "confirmacion_reserva.html",
            reserva=reserva,
            temporal=False
        )

    mensaje = (
        "El tiempo para confirmar terminó o la reservación "
        "ya no está disponible."
    )

    if request.is_json:
        return jsonify({
            "ok": False,
            "mensaje": mensaje
        }), 409

    flash(mensaje, "warning")
    return redirect(url_for("reservar"))



@app.route("/recibo-reservacion/<id>")
def ver_recibo_reservacion(id):

    if not ObjectId.is_valid(id):
        abort(404)

    cliente_id = session.get("cliente_reservas_id")

    if not cliente_id:
        abort(404)

    reserva = reservaciones.find_one({
        "_id": ObjectId(id),
        "cliente_id": cliente_id,
        "estado": "Confirmada"
    })

    if reserva is None:
        abort(404)

    reserva["folio"] = str(reserva["_id"])

    return render_template(
        "confirmacion_reserva.html",
        reserva=reserva
    )


@app.route("/cancelar-reservacion-cliente/<id>", methods=["POST"])
def cancelar_reservacion_cliente(id):

    if not ObjectId.is_valid(id):
        abort(404)

    cliente_id = session.get("cliente_reservas_id")

    es_api = request.is_json

    if not cliente_id:

        mensaje = "No tienes permiso para cancelar este apartado."

        if es_api:
            return jsonify({
                "ok": False,
                "mensaje": mensaje
            }), 403

        flash(mensaje, "warning")
        return redirect(url_for("reservar"))

    ahora = hora_utc()

    resultado = reservaciones.update_one(
        {
            "_id": ObjectId(id),
            "cliente_id": cliente_id,
            "estado": "En espera",
            "expires_at": {"$gt": ahora}
        },
        {
            "$set": {
                "estado": "Cancelada",
                "fecha_cancelacion": ahora
            }
        }
    )

    if resultado.modified_count == 1:

        mensaje = "Tu apartado fue cancelado. La mesa está disponible."

        if es_api:
            return jsonify({
                "ok": True,
                "mensaje": mensaje
            })

        flash(mensaje, "success")

    else:

        mensaje = "El apartado ya venció o no se encuentra activo."

        if es_api:
            return jsonify({
                "ok": False,
                "mensaje": mensaje
            }), 409

        flash(mensaje, "warning")

    return redirect(url_for("reservar"))

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
