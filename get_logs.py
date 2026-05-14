import serial
import logging
import threading
import queue
import time
from typing import List
from datetime import datetime

PORT = 'COM3'
BAUDRATE = 115200

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('com_port_log.txt', encoding='utf-8')
    ]
)


def write_all_data(raw_data):
    """Запись всех сырых данных в отдельный файл"""
    hex_string = raw_data.hex()
    with open('all_data.txt', 'a', encoding='utf-8') as file:
        file.write(f"Время: {datetime.now()} Получено {len(raw_data)} байт: {hex_string}\n")


def data_collector(data_queue: queue.Queue, stop_event: threading.Event, description: str = ""):
    """ЕДИНСТВЕННЫЙ поток, который читает данные с COM-порта"""
    ser = None
    try:
        ser = serial.Serial(
            PORT, BAUDRATE, timeout=0.5,  # ВАЖНО: таймаут 0.5 сек для возможности проверки stop_event
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False, rtscts=False, dsrdtr=False
        )
        logging.info(f"==============={description}==============")
        logging.info(f"[COLLECTOR] Порт {PORT} открыт. Начало сбора данных...")

        while not stop_event.is_set():
            try:
                # Читаем с таймаутом, чтобы иметь возможность проверить stop_event
                raw_data = ser.read(ser.in_waiting or 1)
                if raw_data:
                    # Используем put с таймаутом, чтобы не заблокироваться навсегда
                    data_queue.put(raw_data, timeout=0.5)
                else:
                    # Если данных нет, небольшая пауза для снижения нагрузки CPU
                    time.sleep(0.01)
            except queue.Full:
                logging.warning("[COLLECTOR] Очередь переполнена, данные потеряны")
                continue
            except serial.SerialException as e:
                logging.error(f"[COLLECTOR] Ошибка при чтении: {e}")
                break

    except (serial.SerialException, OSError) as e:
        logging.error(f"[COLLECTOR] Ошибка порта: {e}")
    finally:
        if ser and ser.is_open:
            ser.close()
            logging.info("[COLLECTOR] Порт закрыт")


def process_all_data(data_queue: queue.Queue, stop_event: threading.Event):
    """Обработчик для записи ВСЕХ сырых данных в com4_all_data.txt"""
    while not stop_event.is_set():
        try:
            raw_data = data_queue.get(timeout=0.5)
            write_all_data(raw_data)
        except queue.Empty:
            continue
        except Exception as e:
            logging.error(f"[ALL_DATA] Ошибка: {e}")

    # Обрабатываем оставшиеся данные перед выходом
    while not data_queue.empty():
        try:
            raw_data = data_queue.get_nowait()
            write_all_data(raw_data)
        except queue.Empty:
            break
    logging.info("[ALL_DATA] Остановлен")


def parse_packets_by_terminator(data_queue: queue.Queue, stop_event: threading.Event,
                                address_bytes: List[int] = None, check_addresses: bool = False):
    """Обработчик для парсинга пакетов с терминатором 10 83"""
    terminator = bytes([0x10, 0x83])
    prev_time = None
    buffer = bytearray()

    address_bytes_seq = bytes(address_bytes) if address_bytes else None

    logging.info(f"[PARSER] Запущен. Ищем пакеты, заканчивающиеся на {terminator.hex().upper()}...")
    if check_addresses and address_bytes_seq:
        logging.info(f"[PARSER] Проверка адресов включена. Ожидаемые адреса: {address_bytes_seq.hex().upper()}")
    else:
        logging.info("[PARSER] Проверка адресов ОТКЛЮЧЕНА")

    while not stop_event.is_set():
        try:
            data = data_queue.get(timeout=0.5)
            if data:
                buffer.extend(data)

                # ПОСЛЕДОВАТЕЛЬНО ищем и обрабатываем ВСЕ терминаторы
                while True:
                    pos = buffer.find(terminator)
                    if pos == -1:
                        break

                    # Извлекаем пакет от начала буфера до терминатора
                    end_pos = pos + len(terminator)
                    packet = buffer[:end_pos]

                    # Проверка наличия адресов (если включена)
                    address_check_passed = True
                    if check_addresses and address_bytes_seq:
                        if packet.find(address_bytes_seq) == -1:
                            address_check_passed = False
                            logging.debug(f"[PARSER] Адрес не найден в пакете")

                    if address_check_passed:
                        current_time = datetime.now()
                        if prev_time is None:
                            delta_str = "N/A"
                        else:
                            delta_ms = (current_time - prev_time).total_seconds() * 1000
                            delta_str = f"+{delta_ms:.2f}ms"

                        logging.info(
                            f"[PARSER] Пакет ({len(packet)} байт): {packet.hex().upper()} | дельта {delta_str}")
                        prev_time = current_time
                    else:
                        logging.warning(f"[PARSER] Пакет ОТБРОШЕН: {packet.hex().upper()[:100]}...")

                    # Удаляем обработанный пакет из буфера (СДВИГАЕМ НАЧАЛО)
                    buffer = buffer[end_pos:]

        except queue.Empty:
            continue
        except Exception as e:
            logging.error(f"[PARSER] Ошибка: {e}")

    logging.info("[PARSER] Остановлен")


if __name__ == "__main__":
    init_description = input("Что слушаем?\n")

    # Создаём очередь с ограничением размера (чтобы не переполнилась)
    data_queue = queue.Queue(maxsize=1000)
    stop_event = threading.Event()

    # Создаём и запускаем потоки
    threads = [
        threading.Thread(target=data_collector, args=(data_queue, stop_event, init_description), name="Collector"),
        threading.Thread(target=process_all_data, args=(data_queue, stop_event), name="AllDataWriter"),
        threading.Thread(target=parse_packets_by_terminator,
                         args=(data_queue, stop_event, [], False),
                         name="PacketParser")
    ]

    for t in threads:
        t.daemon = False  # Важно: не демоны, чтобы корректно завершились
        t.start()
        print(f"Запущен поток: {t.name}")

    print("\nПрограмма запущена. Нажмите Ctrl+C для остановки...\n")

    try:
        # Ждём завершения (бесконечно)
        while True:
            time.sleep(0.1)
            if not all(t.is_alive() for t in threads):
                break
    except KeyboardInterrupt:
        print("\n\nПолучен сигнал остановки (Ctrl+C)...")
        stop_event.set()  # Сигнализируем всем потокам о завершении

        # Ждём завершения потоков (максимум 3 секунды)
        for t in threads:
            t.join(timeout=3)
            if t.is_alive():
                print(f"Поток {t.name} не завершился вовремя")

        print("Программа остановлена")