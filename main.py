import serial
import time
import sys
from datetime import datetime

# ==================== НАСТРОЙКИ ====================
COM_PORT = 'COM3'  # Замените на ваш порт
BAUDRATE = 115200
INTERVAL_MS = 600  # Фиксированная пауза 600 мс

# Фиксированный блок данных (8 байт)
DATA_BLOCK = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])

# Имя файла для логирования
LOG_FILE = f"com_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"


# ==================== ЛОГИРОВАНИЕ ====================
class Logger:
    """Класс для логирования в файл и консоль"""

    def __init__(self, filename):
        self.filename = filename
        self.file = None

    def open(self):
        """Открыть файл для записи"""
        try:
            self.file = open(self.filename, 'w', encoding='utf-8')
            self.write_header()
            return True
        except Exception as e:
            print(f"Ошибка открытия файла лога: {e}")
            return False

    def write_header(self):
        """Записать заголовок лог-файла"""
        self.file.write("=" * 100 + "\n")
        self.file.write(f"ЛОГ ПЕРЕДАЧИ ДАННЫХ В COM-ПОРТ\n")
        self.file.write(f"Дата и время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.file.write(f"COM-порт: {COM_PORT}\n")
        self.file.write(f"Скорость: {BAUDRATE} бод\n")
        self.file.write(f"Интервал отправки: {INTERVAL_MS} мс\n")
        self.file.write(f"Блок данных: {' '.join(f'{b:02X}' for b in DATA_BLOCK)}\n")
        self.file.write("=" * 100 + "\n\n")
        self.file.flush()

    def log(self, packet_num, counter, counter_hex, addr_hex, data_hex, crc_hex, full_hex):
        """Запись одной записи в лог"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Формируем строку лога
        log_entry = (f"[{timestamp}] "
                     f"Пакет #{packet_num:6d} | "
                     f"Счётчик={counter:20d} | "
                     f"CRC={crc_hex} | "
                     f"Данные: {full_hex}\n")

        # Записываем в файл
        self.file.write(log_entry)
        self.file.flush()  # Немедленная запись на диск

        # Выводим сокращенную версию в консоль
        print(f"[{packet_num:4d}] Счётчик={counter} | "
              f"[СЧ={counter_hex[:20]}...] [АДР={addr_hex}] [ДАН={data_hex}] CRC={crc_hex}")

    def log_error(self, error_msg):
        """Запись ошибки в лог"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_entry = f"[{timestamp}] ОШИБКА: {error_msg}\n"
        self.file.write(log_entry)
        self.file.flush()
        print(f"Ошибка: {error_msg}")

    def close(self):
        """Закрыть файл лога"""
        if self.file:
            self.file.write("\n" + "=" * 100 + "\n")
            self.file.write(f"Лог завершён: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.file.close()
            print(f"\nЛог сохранён в файл: {self.filename}")


# ==================== ВВОД АДРЕСА ====================
def get_object_address():
    """Запрос адреса объекта у пользователя"""
    while True:
        try:
            addr_input = input("Введите адрес объекта (2 байта в HEX, например: 01 A0 или 0x01 0xA0): ").strip()

            # Убираем префиксы 0x и разделители
            addr_input = addr_input.replace('0x', '').replace(',', ' ').replace(';', ' ')
            parts = addr_input.split()

            if len(parts) == 2:
                # Два отдельных байта
                addr_bytes = bytes([int(p, 16) for p in parts])
            elif len(parts) == 1:
                # Один 16-битный адрес
                val = int(parts[0], 16)
                addr_bytes = bytes([(val >> 8) & 0xFF, val & 0xFF])
            else:
                print("Ошибка: нужно ввести 2 байта (например: 01 A0)")
                continue

            print(f"Адрес объекта: {addr_bytes[0]:02X} {addr_bytes[1]:02X}")
            return addr_bytes

        except ValueError:
            print("Ошибка: неверный формат. Примеры: '01 A0', '0x01 0xA0', '01A0'")


# ==================== CRC-8 ====================
def calculate_crc8(data: bytes, polynomial=0x07, init=0x00):
    """
    Расчет CRC-8 с полиномом 0x07 (стандарт для Dallas/Maxim)
    data: байты для расчета CRC
    polynomial: полином (0x07 - стандартный CRC-8)
    init: начальное значение
    """
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ polynomial
            else:
                crc <<= 1
            crc &= 0xFF  # Ограничиваем 8 битами
    return crc


# ==================== СЧЁТЧИК (14 БАЙТ) ====================
def counter_to_14_bytes(counter: int) -> bytes:
    """
    Преобразует целочисленный счётчик в 14 байт (big-endian)
    """
    return counter.to_bytes(14, byteorder='big')


# ==================== ФОРМИРОВАНИЕ ТЕЛЕГРАММЫ ====================
def build_telegram(counter: int, object_address: bytes, data_block: bytes) -> bytes:
    """
    Формирует полную телеграмму:
    - Счётчик (14 байт)
    - 2 байта адреса
    - 8 байт данных
    - 1 байт CRC-8
    """
    # Счётчик в 14 байт
    counter_bytes = counter_to_14_bytes(counter)

    # Собираем телеграмму без CRC
    telegram_without_crc = counter_bytes + object_address + data_block

    # Рассчитываем CRC-8
    crc = calculate_crc8(telegram_without_crc)

    # Полная телеграмма
    full_telegram = telegram_without_crc + bytes([crc])

    return full_telegram


# ==================== ОСНОВНАЯ ПРОГРАММА ====================
def main():
    print("=" * 60)
    print("Программа отправки данных в COM-порт")
    print("=" * 60)

    # Инициализация логгера
    logger = Logger(LOG_FILE)
    if not logger.open():
        print("Невозможно создать файл лога. Программа остановлена.")
        sys.exit(1)

    # Запрашиваем адрес объекта
    object_address = get_object_address()

    # Параметры
    counter = 0
    packet_count = 0

    try:
        # Открываем COM-порт
        with serial.Serial(COM_PORT, BAUDRATE, timeout=1) as ser:
            print(f"\nПодключено к {COM_PORT} на скорости {BAUDRATE} бод")
            print(f"Интервал отправки: {INTERVAL_MS} мс")
            print(f"Блок данных: {' '.join(f'{b:02X}' for b in DATA_BLOCK)}")
            print(f"Размер счётчика: 14 байт")
            print(f"Общий размер телеграммы: 14 + 2 + 8 + 1 = 25 байт")
            print(f"Лог-файл: {LOG_FILE}")
            print("\nОтправка... Нажмите Ctrl+C для остановки\n")
            print("-" * 80)

            while True:
                # Формируем телеграмму
                telegram = build_telegram(counter, object_address, DATA_BLOCK)

                # Отправляем
                ser.write(telegram)
                packet_count += 1

                # Формируем hex-представления для вывода
                counter_hex = ' '.join(f'{b:02X}' for b in telegram[0:14])
                addr_hex = ' '.join(f'{b:02X}' for b in telegram[14:16])
                data_hex = ' '.join(f'{b:02X}' for b in telegram[16:24])
                crc_hex = f'{telegram[24]:02X}'
                full_hex = ' '.join(f'{b:02X}' for b in telegram)

                # Логируем отправку
                logger.log(packet_count, counter, counter_hex, addr_hex, data_hex, crc_hex, full_hex)

                # Инкрементируем счётчик (автоматически)
                counter += 1

                # Фиксированная пауза 600 мс
                time.sleep(INTERVAL_MS / 1000.0)

    except serial.SerialException as e:
        error_msg = f"Ошибка COM-порта: {e}\nПроверьте, что порт {COM_PORT} существует и не занят"
        logger.log_error(error_msg)
        print(error_msg)
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n\nПрограмма остановлена. Отправлено пакетов: {packet_count}")
        logger.close()
        sys.exit(0)
    except Exception as e:
        error_msg = f"Непредвиденная ошибка: {e}"
        logger.log_error(error_msg)
        print(error_msg)
        logger.close()
        sys.exit(1)


if __name__ == "__main__":
    main()