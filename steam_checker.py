import requests
import json
import os
import logging
from datetime import datetime
import time

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('steam_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Archivos de configuración
CONFIG_FILE = "config.json"
DB_FILE = "precios_vistos.json"

def load_config():
    """Carga la configuración desde config.json"""
    default_config = {
        "apps": {
            "1085660": "Destiny 2 (Base)",
            "1090150": "Destiny 2: Forsaken Pack"
        },
        "region": "co",
        "language": "spanish",
        "check_interval_hours": 6,
        "notifications": {
            "min_discount_percent": 10,
            "only_notify_on_discount": True
        }
    }
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            
            # Combinar con valores por defecto
            config = {**default_config, **user_config}
            
            # Combinar apps (los del usuario tienen prioridad)
            if "apps" in user_config:
                config["apps"] = {**default_config["apps"], **user_config["apps"]}
            
            logger.info(f"Configuración cargada: {len(config['apps'])} apps")
            return config
        else:
            logger.warning(f"Archivo {CONFIG_FILE} no encontrado, usando configuración por defecto")
            return default_config
    except json.JSONDecodeError as e:
        logger.error(f"Error en formato de {CONFIG_FILE}: {e}")
        return default_config
    except Exception as e:
        logger.error(f"Error cargando configuración: {e}")
        return default_config

def load_history():
    """Carga el historial de precios desde el archivo JSON"""
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error cargando historial: {e}")
        return {}

def save_history(history):
    """Guarda el historial de precios en el archivo JSON"""
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        logger.info("Historial guardado exitosamente")
    except IOError as e:
        logger.error(f"Error guardando historial: {e}")

def send_discord_notification(message, app_name, current_price, discount_percent, original_price=None, app_id=None):
    """Envía una notificación embellecida a Discord"""
    
    # Determinar color según descuento
    if discount_percent >= 75:
        color = 0x00ff00  # Verde para grandes descuentos
    elif discount_percent >= 50:
        color = 0xffa500  # Naranja
    elif discount_percent >= 25:
        color = 0xffff00  # Amarillo
    else:
        color = 0xff0000  # Rojo para descuentos menores
    
    # Construir URL de Steam
    steam_url = f"https://store.steampowered.com/app/{app_id}" if app_id else "https://store.steampowered.com"
    
    embed = {
        "title": "🎮 ¡Nueva Oferta en Steam!",
        "description": message,
        "color": color,
        "url": steam_url,
        "fields": [
            {
                "name": "Juego",
                "value": f"[{app_name}]({steam_url})",
                "inline": True
            },
            {
                "name": "Descuento",
                "value": f"**-{discount_percent}%**",
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
    
    if original_price and original_price != current_price:
        embed["fields"].append({
            "name": "Precio Original",
            "value": f"~~{original_price}~~",
            "inline": False
        })
    
    payload = {
        "embeds": [embed],
        "username": "Steam Price Bot",
        "avatar_url": "https://cdn.iconscout.com/icon/free/png-256/steam-3-226995.png"
    }
    
    try:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            logger.error("DISCORD_WEBHOOK_URL no está configurado")
            return False
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            logger.info(f"✅ Notificación enviada para {app_name}")
            return True
        else:
            logger.error(f"❌ Error al enviar notificación: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error de conexión con Discord: {e}")
        return False

def check_steam_prices(config):
    """Consulta los precios de Steam para las apps configuradas"""
    history = load_history()
    all_apps_data = {}
    apps_checked = 0
    notifications_sent = 0
    
    APPS = config["apps"]
    REGION = config["region"]
    LANGUAGE = config["language"]
    MIN_DISCOUNT = config["notifications"]["min_discount_percent"]
    
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # Consultar cada app individualmente
    for app_id, app_name in APPS.items():
        try:
            logger.info(f"🔍 Consultando {app_name} (ID: {app_id})...")
            
            url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc={REGION}&l={LANGUAGE}"
            
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": f"{LANGUAGE};q=0.9"
            }
            
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            
            data = response.json()
            
            if app_id in data and data[app_id]["success"]:
                app_data = data[app_id]["data"]
                apps_checked += 1
                
                # Verificar si es gratis
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
                    logger.warning(f"⚠️ {app_name} no tiene información de precio")
                    continue
                
                # Guardar datos
                all_apps_data[app_id] = {
                    "name": app_name,
                    "current_price": current_price,
                    "price_formatted": price_formatted,
                    "original_price_formatted": original_price_formatted,
                    "discount_percent": discount_percent,
                    "last_checked": datetime.now().isoformat()
                }
                
                logger.info(f"💰 {app_name}: {price_formatted} (-{discount_percent}%)")
                
                # Verificar si hay cambio significativo
                should_notify = False
                notification_reason = ""
                
                if app_id not in history:
                    # Primera vez que se verifica
                    if discount_percent >= MIN_DISCOUNT:
                        should_notify = True
                        notification_reason = "Nueva verificación con descuento"
                elif current_price < history[app_id].get("last_price", float('inf')):
                    # El precio bajó
                    should_notify = True
                    notification_reason = "Precio reducido"
                elif discount_percent > history[app_id].get("last_discount", 0):
                    # Descuento aumentó
                    should_notify = True
                    notification_reason = "Descuento aumentado"
                elif discount_percent >= MIN_DISCOUNT and history[app_id].get("last_discount", 0) == 0:
                    # Nuevo descuento
                    should_notify = True
                    notification_reason = "Nuevo descuento"
                
                # Enviar notificación si es necesario
                if should_notify and discount_percent >= MIN_DISCOUNT:
                    message = f"🔥 **{notification_reason}**"
                    if send_discord_notification(
                        message=message,
                        app_name=app_name,
                        current_price=price_formatted,
                        discount_percent=discount_percent,
                        original_price=original_price_formatted,
                        app_id=app_id
                    ):
                        notifications_sent += 1
                
                # Actualizar historial
                history[app_id] = {
                    "last_price": current_price,
                    "last_discount": discount_percent,
                    "last_notification": datetime.now().isoformat() if should_notify else history.get(app_id, {}).get("last_notification", ""),
                    "name": app_name,
                    "last_checked": datetime.now().isoformat()
                }
                
            else:
                logger.error(f"❌ Error en datos de {app_name}")
            
            # Esperar entre consultas
            time.sleep(2)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Error de conexión para {app_name}: {e}")
        except KeyError as e:
            logger.error(f"🔑 Error en estructura de datos para {app_name}: {e}")
        except Exception as e:
            logger.error(f"⚠️ Error inesperado con {app_name}: {e}")
    
    # Guardar historial actualizado
    save_history(history)
    
    return all_apps_data, apps_checked, notifications_sent

def generate_report(all_apps_data, apps_checked, notifications_sent):
    """Genera un reporte de la ejecución"""
    logger.info("=" * 60)
    logger.info("📊 RESUMEN DE LA EJECUCIÓN")
    logger.info("=" * 60)
    
    # Contar juegos con descuento
    games_with_discount = sum(1 for data in all_apps_data.values() if data["discount_percent"] > 0)
    free_games = sum(1 for data in all_apps_data.values() if data["price_formatted"] == "Gratis")
    
    logger.info(f"✅ Juegos verificados: {apps_checked}/{len(all_apps_data)}")
    logger.info(f"🎯 Con descuento: {games_with_discount}")
    logger.info(f"🆓 Gratis: {free_games}")
    logger.info(f"🔔 Notificaciones enviadas: {notifications_sent}")
    
    # Mostrar precios actuales
    logger.info("\n💸 PRECIOS ACTUALES:")
    for app_id, data in sorted(all_apps_data.items(), key=lambda x: x[1]["discount_percent"], reverse=True):
        discount_symbol = "🔥" if data["discount_percent"] > 0 else "  "
        logger.info(f"{discount_symbol} {data['name']}: {data['price_formatted']} (-{data['discount_percent']}%)")
    
    logger.info("=" * 60)

def main():
    """Función principal"""
    logger.info("=" * 60)
    logger.info("🚀 INICIANDO STEAM PRICE TRACKER")
    logger.info("=" * 60)
    
    # Verificar variables de entorno
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("⚠️ DISCORD_WEBHOOK_URL no está configurado")
        logger.warning("💡 Configura: export DISCORD_WEBHOOK_URL='tu_url'")
    
    # Cargar configuración
    config = load_config()
    logger.info(f"🌎 Región: {config['region']}")
    logger.info(f"🗣️ Idioma: {config['language']}")
    logger.info(f"📱 Apps monitoreadas: {len(config['apps'])}")
    
    try:
        # Verificar precios
        all_apps_data, apps_checked, notifications_sent = check_steam_prices(config)
        
        # Generar reporte
        generate_report(all_apps_data, apps_checked, notifications_sent)
        
    except Exception as e:
        logger.error(f"💥 Error en ejecución principal: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)