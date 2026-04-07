import serial
import logging
from datetime import datetime

PORT = 'COM3'  # Укажите ваш порт
BAUDRATE = 115200  # Скорость передачи

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),                     # вывод в консоль
        logging.FileHandler('com_port_log.txt', encoding='utf-8')  # вывод в файл
    ]
)

def read_hex_dump():
    ser = None
    # ports = serial.tools.list_ports.comports()
    # for port in ports:
    #     print(f"{port.device} - {port.description}")
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=1, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=True)
        logging.info(f"Порт {PORT} открыт. Ожидание данных...")

        while True:
            if ser.in_waiting > 0:
                raw_data = ser.read(ser.in_waiting)
                hex_string = raw_data.hex()  # Конвертация bytes -> HEX строка
                # Выводим в консоль с информацией о количестве байт
                logging.info(f"Получено {len(raw_data)} байт: {hex_string}")

    except (serial.SerialException, OSError) as e:
        logging.error(f"Ошибка порта: {e}")
    finally:
        # Корректно закрываем порт перед выходом
        if ser is not None and ser.is_open:
            ser.close()
            logging.info("Порт закрыт.")


if __name__ == "__main__":
    read_hex_dump()