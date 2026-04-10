import serial
import logging
from typing import List
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
def write_all_data(raw_data):
    hex_string = raw_data.hex()
    with open('all_data.txt', 'a', encoding='utf-8') as file:
        file.write(f"Время: {datetime.now()} Получено {len(raw_data)} байт: {hex_string}\n")

def read_hex_dump():
    ser = None
    # ports = serial.tools.list_ports.comports()
    # for port in ports:
    #     print(f"{port.device} - {port.description}")
    try:
        ser = serial.Serial(
            PORT,
            BAUDRATE,
            timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,  # Отключено для RS-422
            rtscts=False,  # Отключено для RS-422
            dsrdtr=False  # Отключено для RS-422
        )
        logging.info(f"Порт {PORT} открыт. Ожидание данных...")

        while True:
            if ser.in_waiting > 0:
                raw_data = ser.read(ser.in_waiting)
                hex_string = raw_data.hex()  # Конвертация bytes -> HEX строка
                # Выводим в консоль с информацией о количестве байт
                # logging.info(f"Получено hex данных {len(raw_data)} байт: {hex_string}")
                logging.info(f"Получены сырые данные: {raw_data}")
                # logging.info(f"Получен список целочисл значений: {list(raw_data)}")

    except (serial.SerialException, OSError) as e:
        logging.error(f"Ошибка порта: {e}")
    finally:
        # Корректно закрываем порт перед выходом
        if ser is not None and ser.is_open:
            ser.close()
            logging.info("Порт закрыт.")


def read_packets_by_marker_variable(port: str, baudrate: int, marker: List[int], prefix_len: int = 14):
    """
    Читает поток с COM-порта, выделяет пакеты, начинающиеся с
    [prefix_len байт] + [2 байта маркера] и продолжающиеся до следующего
    такого же заголовка (или до конца данных).

    :param port: имя COM-порта
    :param baudrate: скорость
    :param marker: список из двух целых чисел (0-255), например [0x48, 0x61]
    :param prefix_len: количество байт перед маркером (по умолчанию 14)
    """
    marker_bytes = bytes(marker)  # b'\x48\x61'
    header_len = prefix_len + len(marker_bytes)  # 16 байт
    prev_time = None  # время предыдущего пакета

    ser = None
    buffer = bytearray()

    try:
        ser = serial.Serial(port, baudrate, timeout=0.1)
        logging.info(f"Порт {port} открыт. Ищем заголовки {marker_bytes.hex().upper()}...")

        while True:
            # Читаем все доступные данные
            data = ser.read(ser.in_waiting or 1024)
            if data:
                # write_all_data(data)
                buffer.extend(data)
                logging.debug(f"Буфер пополнен, размер {len(buffer)} байт")

            # Поиск всех заголовков в буфере
            # Заголовок — это позиция, где найден marker_bytes и перед ним есть prefix_len байт
            headers_positions = []
            pos = 0
            while True:
                pos = buffer.find(marker_bytes, pos)
                if pos == -1:
                    break
                if pos >= prefix_len:
                    headers_positions.append(pos - prefix_len)  # сохраняем начало заголовка
                pos += len(marker_bytes)

            # Если найдено хотя бы два заголовка, можем извлечь пакет
            if len(headers_positions) >= 2:
                start = headers_positions[0]
                end = headers_positions[1]  # начало следующего пакета
                packet = buffer[start:end]

                # Вычисляем дельту времени
                current_time = datetime.now()
                if prev_time is None:
                    delta_str = "N/A"
                else:
                    delta_ms = (current_time - prev_time).total_seconds() * 1000
                    delta_str = f"+{delta_ms:.2f}ms"

                logging.info(f"Пакет ({len(packet)} байт): {packet.hex().upper()} | дельта {delta_str}")

                prev_time = current_time

                # Удаляем обработанные байты из буфера
                buffer = buffer[end:]
            elif len(headers_positions) == 1:
                # Есть только один заголовок, ждём следующий
                # Чтобы буфер не рос бесконечно, можно ограничить его размер
                if len(buffer) > 10000:
                    # Если буфер слишком велик, но второго заголовка нет — вероятно, потерян конец пакета
                    # Можно вывести то, что есть, и очистить
                    logging.warning("Буфер переполнен, сброс")
                    buffer.clear()
                # Небольшая пауза для снижения нагрузки CPU
                # time.sleep(0.001)
            else:
                # Нет ни одного заголовка — ждём данные
                if len(buffer) > 10000:
                    buffer.clear()
                    logging.warning("Буфер переполнен, очищен")

    except (serial.SerialException, OSError) as e:
        logging.error(f"Ошибка порта: {e}")
    except KeyboardInterrupt:
        logging.info("Остановка пользователем")
    finally:
        if ser and ser.is_open:
            ser.close()
            logging.info("Порт закрыт")


if __name__ == "__main__":
    read_hex_dump()
    # read_packets_by_marker_variable(PORT, BAUDRATE, marker=[0x58, 0x63], prefix_len=14)