# ☕ Dreamy Coffee

## 1. Descripción del proyecto

Dreamy Coffee es una aplicación web desarrollada con Flask y Python que permite administrar una cafetería. Su objetivo es facilitar la consulta de productos, la realización de pedidos y la reservación de mesas mediante una página web.

## 2. Integrantes

- Sanchez Osorio Samantha Michelle
- Chuc Mayo Valeria Noemi

## 3. Problema que resuelve

El proyecto busca facilitar la administración de una cafetería y mejorar la experiencia de los clientes, permitiéndoles consultar el menú, realizar pedidos y reservar mesas sin tener que hacer todos estos procesos presencialmente.

## 4. Sistema de reservación temporal

La aplicación permite reservar mesas de la cafetería.

- **Elemento reservado:** mesas de la cafetería.
- **Cantidad de mesas:** 6.
- **Duración del apartado temporal:** 60 segundos.
- **Estados:** Disponible, En proceso y Confirmada.

Cuando un cliente comienza una reservación, la mesa queda apartada temporalmente. Si no confirma dentro del tiempo establecido, vuelve a estar disponible para otros clientes.

## 5. Función del código QR

La aplicación cuenta con una función para generar códigos QR individuales para cada reservación confirmada.

Cuando un cliente confirma su reservación, el sistema genera un folio único y crea un código QR asociado a esa reservación. El cliente puede visualizarlo y descargarlo en formato PDF para presentarlo cuando llegue a la cafetería.

Al escanear el código QR, se abre una página pública de Dreamy Coffee donde se muestra la información de la reservación, como:

- Folio de reservación.
- Fecha.
- Horario.
- Número de mesa.
- Ubicación de la mesa (interior o exterior).
- Duración de la reservación.
- Estado de la reservación.

De esta manera, cada código QR permite consultar los datos correspondientes a una reservación específica, facilitando la identificación y verificación de las reservas de los clientes.

## 6. Tecnologías utilizadas

- Python
- Flask
- MongoDB Atlas
- HTML
- CSS
- JavaScript
- Git y GitHub
- Render

## 7. Instrucciones de ejecución

Para ejecutar el proyecto Dreamy Coffee en un entorno local, sigue estos pasos:

1. **Clonar o descargar el repositorio.** Obtener los archivos del proyecto desde GitHub.

2. **Abrir la carpeta del proyecto.** Abrirla en Visual Studio Code o en una terminal.

3. **Crear un entorno virtual.** Ejecutar el siguiente comando:
   ```bash
   python -m venv .venv
   ```

4. **Activar el entorno virtual.** En Windows PowerShell:
   ```powershell
   .venv\Scripts\Activate
   ```

5. **Instalar las dependencias.** Ejecutar:
   
   pip install -r requirements.txt


6. **Configurar las variables de entorno.** Crear un archivo `.env` en la carpeta principal del proyecto y agregar las variables necesarias:
   - `FLASK_SECRET_KEY`
   - `MONGO_URI`
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD_HASH`

7. **Ejecutar la aplicación.** Iniciar el servidor local con:
   
   python app.py


8. **Abrir la aplicación en el navegador.** Ingresar a:
   
   http://127.0.0.1:5000
   

## 8. Variables de entorno necesarias

Crear un archivo `.env` en la carpeta principal del proyecto con las siguientes variables:

```env
FLASK_SECRET_KEY=
MONGO_URI=
ADMIN_USERNAME=
ADMIN_PASSWORD_HASH=
```

## 9. Enlace de la aplicación

**Render:**(https://cafeteria-dreamycoffe.onrender.com)

**GitHub:** https://github.com/sanchezosoriosamanthamichelle/cafeteria-dreamycoffe.git

## 10. Capturas principales

Agregar capturas de pantalla de:

- Página de inicio.
![Pagina prinicpal antes de actualizaciones](inicio-antes.png)
![pagina principal despues de modificar la interfaz](inicio-despues.png)
- Menú de productos.
![Menu de todos los productos](menu.png)
- Carrito y realización de pedidos.
![Productos agregados al carrito](carrito.png)
![Finalizar un pedido ](finalizar-pedido.png)
- Panel de administración.
![Agregar producto](admin1-1.png)
![Productos registrados](admin2.png)
![Pedidos registrados](admin3.png)
![Version actual](admin-actual.png)

- Proceso de apartado temporal.
![Apartado de una mesa](reservacion.png)
![Recibo despues de confirmar la reserva](recibo.png)
- Ficha pública y código QR.
![Generacion del codigo qr despues de la reserva](qr.png)