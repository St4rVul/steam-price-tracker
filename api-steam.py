import requests
import json
import os
import logging
from datetime import datetime
import time

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuración (mover a variables de entorno en producción)
APPS = {
    "1085660": "Destiny 2 (Base)",
    "1090150": "Destiny 2: Forsaken Pack"
}
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "TU_URL_AQUI")
DB_FILE = "precios_vistos.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def load_history():
    """Carga el historial de precios desde el archivo JSON"""
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        return {}
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error cargando historial: {e}")
        return {}

def save_history(history):
    """Guarda el historial de precios en el archivo JSON"""
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        logger.info("Historial guardado exitosamente")
    except IOError as e:
        logger.error(f"Error guardando historial: {e}")

def send_discord_notification(message, app_name, current_price, discount_percent, original_price=None):
    """Envía una notificación embellecida a Discord"""
    
    # Determinar color según descuento
    if discount_percent >= 75:
        color = 0x00ff00  # Verde para grandes descuentos
    elif discount_percent >= 50:
        color = 0xffa500  # Naranja
    else:
        color = 0xff0000  # Rojo para descuentos menores
    
    embed = {
        "title": "🎮 ¡Nueva Oferta en Steam!",
        "description": message,
        "color": color,
        "fields": [
            {
                "name": "Juego",
                "value": app_name,
                "inline": True
            },
            {
                "name": "Descuento",
                "value": f"-{discount_percent}%",
                "inline": True
            },
            {
                "name": "Precio Actual",
                "value": f"**{current_price}**",
                "inline": True
            }
        ],
        "footer": {
            "text": f"Steam Price Tracker • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        },
        "thumbnail": {
            "url": "https://cdn.iconscout.com/icon/free/png-256/steam-3-226995.png"
        }
    }
    
    if original_price:
        embed["fields"].append({
            "name": "Precio Original",
            "value": f"~~{original_price}~~",
            "inline": True
        })
    
    payload = {
        "embeds": [embed],
        "username": "Steam Price Bot",
        "avatar_url": "https://cdn.iconscout.com/icon/free/png-256/steam-3-226995.png"
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 204:
            logger.info(f"Notificación enviada para {app_name}")
        else:
            logger.error(f"Error al enviar notificación: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión con Discord: {e}")

def check_steam_prices():
    """Consulta los precios de Steam para las apps configuradas"""
    history = load_history()
    all_apps_data = {}
    
    # Consultar cada app individualmente para mejor manejo de errores
    for app_id, app_name in APPS.items():
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=co&l=spanish"
            
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "es-CO,es;q=0.9"
            }
            
            logger.info(f"Consultando precio para {app_name} (ID: {app_id})")
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if app_id in data and data[app_id]["success"]:
                app_data = data[app_id]["data"]
                
                # Verificar si es gratis o tiene precio
                if app_data.get("is_free", False):
                    current_price = 0
                    price_formatted = "Gratis"
                    discount_percent = 100
                    original_price_formatted = "Gratis"
                elif "price_overview" in app_data:
                    price_info = app_data["price_overview"]
                    current_price = price_info["final"]
                    price_formatted = price_info["final_formatted"]
                    discount_percent = price_info.get("discount_percent", 0)
                    original_price_formatted = price_info.get("initial_formatted", price_formatted)
                else:
                    logger.warning(f"{app_name} no tiene información de precio disponible")
                    continue
                
                # Guardar datos de la app
                all_apps_data[app_id] = {
                    "name": app_name,
                    "current_price": current_price,
                    "price_formatted": price_formatted,
                    "original_price_formatted": original_price_formatted,
                    "discount_percent": discount_percent,
                    "last_checked": datetime.now().isoformat()
                }
                
                logger.info(f"{app_name}: {price_formatted} (Descuento: {discount_percent}%)")
                
                # Verificar si hay cambio de precio o nuevo descuento
                should_notify = False
                
                if app_id not in history:
                    # Primera vez que se verifica este juego
                    should_notify = discount_percent > 0
                elif current_price < history[app_id].get("last_price", float('inf')):
                    # El precio bajó desde la última vez
                    should_notify = True
                elif discount_percent > 0 and history[app_id].get("last_discount", 0) == 0:
                    # Nuevo descuento (antes no había)
                    should_notify = True
                elif discount_percent > history[app_id].get("last_discount", 0):
                    # El descuento aumentó
                    should_notify = True
                
                # Enviar notificación si es necesario
                if should_notify and discount_percent > 0:
                    message = f"🔥 **¡Oferta disponible!**"
                    send_discord_notification(
                        message=message,
                        app_name=app_name,
                        current_price=price_formatted,
                        discount_percent=discount_percent,
                        original_price=original_price_formatted
                    )
                
                # Actualizar historial
                history[app_id] = {
                    "last_price": current_price,
                    "last_discount": discount_percent,
                    "last_update": datetime.now().isoformat(),
                    "name": app_name
                }
                
            else:
                logger.error(f"Error en datos de {app_name}")
                
            # Esperar entre consultas para no sobrecargar la API
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de conexión para {app_name}: {e}")
        except KeyError as e:
            logger.error(f"Error en estructura de datos para {app_name}: {e}")
        except Exception as e:
            logger.error(f"Error inesperado con {app_name}: {e}")
    
    # Guardar historial actualizado
    save_history(history)
    
    return all_apps_data

def main():
    """Función principal"""
    logger.info("=" * 50)
    logger.info("Iniciando verificación de precios de Steam")
    logger.info("=" * 50)
    
    try:
        results = check_steam_prices()
        
        logger.info("=" * 50)
        logger.info("Resumen de precios:")
        for app_id, data in results.items():
            logger.info(f"{data['name']}: {data['price_formatted']} (-{data['discount_percent']}%)")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"Error en ejecución principal: {e}")

if __name__ == "__main__":
    main()