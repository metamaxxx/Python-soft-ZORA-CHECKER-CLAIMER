from web3 import Web3
from eth_account import Account
import json
from dotenv import load_dotenv
import os
import time
import random
from eth_account.messages import encode_defunct
from datetime import datetime, timedelta

# Загрузка переменных окружения
load_dotenv()

# Настройка подключения к Base
RPC_URL = "https://base-rpc.publicnode.com"
web3 = Web3(Web3.HTTPProvider(RPC_URL))

# Настройки задержки между транзакциями (в секундах)
MIN_DELAY = 5
MAX_DELAY = 10

# Адрес контракта
CONTRACT_ADDRESS = "0x0000000002ba96c69b95e32caab8fc38bab8b3f8"

# Загрузка ABI из файла
with open('contract_abi.json', 'r') as f:
    CONTRACT_ABI = json.load(f)

# Инициализация контракта
contract = web3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

def load_wallets(filename='wallets.txt'):
    """Загрузка адресов кошельков из файла"""
    try:
        with open(filename, 'r') as f:
            wallets = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        return wallets
    except FileNotFoundError:
        print(f"Файл {filename} не найден. Создайте файл и добавьте адреса кошельков (по одному на строку).")
        return []

def load_private_keys(filename='private_keys.txt'):
    """Загрузка приватных ключей из файла"""
    try:
        with open(filename, 'r') as f:
            keys = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        return keys
    except FileNotFoundError:
        print(f"Файл {filename} не найден. Создайте файл и добавьте приватные ключи (по одному на строку).")
        return []

def check_allocation(address):
    """Проверка аллокации для адреса"""
    try:
        result = contract.functions.accountClaim(Web3.to_checksum_address(address)).call()
        allocation = result[0]
        claimed = result[1]
        
        return {
            'address': address,
            'allocation': Web3.from_wei(allocation, 'ether'),
            'claimed': claimed
        }
    except Exception as e:
        return {
            'address': address,
            'error': str(e)
        }

def check_all_allocations():
    """Массовая проверка аллокаций"""
    wallets = load_wallets()
    if not wallets:
        return
    
    print("\nПроверка аллокаций для кошельков:")
    print("-" * 80)
    print(f"{'Адрес':<45} | {'Аллокация':>15} | {'Статус':<10}")
    print("-" * 80)
    
    for wallet in wallets:
        result = check_allocation(wallet)
        if 'error' in result:
            print(f"{result['address']:<45} | {'Ошибка':>15} | {result['error']:<10}")
        else:
            status = "Получено" if result['claimed'] else "Доступно"
            print(f"{result['address']:<45} | {result['allocation']:>15.2f} | {status:<10}")
        time.sleep(0.1)  # Задержка между запросами
    
    print("-" * 80)

def get_signature(private_key, user_address, claim_to_address, deadline):
    """Получение подписи для claimWithSignature"""
    # Создаем сообщение для подписи
    message = Web3.solidity_keccak(
        ['address', 'address', 'uint256'],
        [
            Web3.to_checksum_address(user_address),
            Web3.to_checksum_address(claim_to_address),
            deadline
        ]
    )
    
    # Подписываем сообщение
    signed_message = web3.eth.account.sign_message(
        encode_defunct(message),
        private_key=private_key
    )
    
    return signed_message.signature

def claim_tokens(private_key, wallet_address):
    """Клейм токенов"""
    try:
        account = Account.from_key(private_key)
        
        # Проверяем, что адрес кошелька соответствует приватному ключу
        if account.address.lower() != wallet_address.lower():
            return {
                'success': False,
                'address': wallet_address,
                'error': 'Приватный ключ не соответствует адресу кошелька'
            }

        # Подготовка транзакции
        nonce = web3.eth.get_transaction_count(account.address)
        
        # Создаем транзакцию с увеличенным газом
        transaction = contract.functions.claim(
            Web3.to_checksum_address(wallet_address)
        ).build_transaction({
            'from': account.address,
            'gas': 72038,  # Устанавливаем газ как в успешной транзакции
            'maxFeePerGas': web3.eth.gas_price,  # Используем текущую цену газа
            'maxPriorityFeePerGas': web3.to_wei('0.00000005', 'gwei'),  # Устанавливаем как в успешной транзакции
            'nonce': nonce,
            'type': 2  # EIP-1559 транзакция
        })

        # Подписание и отправка транзакции
        signed_txn = web3.eth.account.sign_transaction(transaction, private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        return {
            'success': True,
            'address': wallet_address,
            'tx_hash': tx_hash.hex()
        }
    
    except Exception as e:
        return {
            'success': False,
            'address': wallet_address,
            'error': str(e)
        }

def claim_all_tokens():
    """Массовый клейм токенов"""
    wallets = load_wallets()
    private_keys = load_private_keys()
    
    if not wallets or not private_keys:
        return
    
    if len(wallets) != len(private_keys):
        print("\nОшибка: Количество адресов и приватных ключей не совпадает!")
        print(f"Адресов: {len(wallets)}, Приватных ключей: {len(private_keys)}")
        return
    
    print("\nНачинаем массовый клейм токенов:")
    print("-" * 130)
    print(f"{'Адрес':<45} | {'Статус':<75}")
    print("-" * 130)
    
    for wallet, private_key in zip(wallets, private_keys):
        # Проверяем аллокацию перед клеймом
        allocation = check_allocation(wallet)
        if 'error' in allocation:
            print(f"{wallet:<45} | Ошибка: {allocation['error']:<75}")
            continue
            
        if allocation['claimed']:
            print(f"{wallet:<45} | Токены уже получены")
            continue
            
        # Пытаемся выполнить клейм
        result = claim_tokens(private_key, wallet)
        if result['success']:
            tx_link = f"https://basescan.org/tx/{result['tx_hash']}"
            print(f"{result['address']:<45} | Успешно: {result['tx_hash']}")
            print(f"{'':<45} | Ссылка: {tx_link}")
        else:
            print(f"{result['address']:<45} | Ошибка: {result['error']}")
        
        # Случайная задержка между транзакциями
        if wallet != wallets[-1]:  # Не делаем задержку после последнего кошелька
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            print(f"\nОжидаем {delay:.1f} секунд перед следующей транзакцией...")
            time.sleep(delay)
    
    print("-" * 130)

def main():
    while True:
        print("\n1. Проверить аллокации всех кошельков")
        print("2. Проверить аллокацию одного кошелька")
        print("3. Клеймить токены для одного кошелька")
        print("4. Клеймить токены для всех кошельков")
        print("5. Изменить настройки задержки")
        print("6. Выход")
        
        choice = input("\nВыберите действие (1-6): ")
        
        if choice == "1":
            check_all_allocations()
            
        elif choice == "2":
            address = input("Введите адрес для проверки: ")
            result = check_allocation(address)
            if 'error' in result:
                print(f"\nОшибка для адреса {result['address']}: {result['error']}")
            else:
                status = "Получено" if result['claimed'] else "Доступно"
                print(f"\nРезультаты для адреса {result['address']}:")
                print(f"Аллокация: {result['allocation']} токенов")
                print(f"Статус: {status}")
            
        elif choice == "3":
            address = input("Введите адрес кошелька: ")
            private_key = input("Введите приватный ключ от этого кошелька: ")
            
            result = claim_tokens(private_key, address)
            if result['success']:
                print(f"\nТранзакция отправлена. Хэш: {result['tx_hash']}")
            else:
                print(f"\nОшибка: {result['error']}")
            
        elif choice == "4":
            claim_all_tokens()
            
        elif choice == "5":
            global MIN_DELAY, MAX_DELAY
            try:
                min_delay = float(input("Введите минимальную задержку (в секундах): "))
                max_delay = float(input("Введите максимальную задержку (в секундах): "))
                if min_delay < 0 or max_delay < 0 or min_delay > max_delay:
                    print("\nОшибка: Некорректные значения задержки")
                else:
                    MIN_DELAY = min_delay
                    MAX_DELAY = max_delay
                    print(f"\nНастройки задержки обновлены: {MIN_DELAY}-{MAX_DELAY} секунд")
            except ValueError:
                print("\nОшибка: Введите числовые значения")
            
        elif choice == "6":
            break
            
        else:
            print("Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    if web3.is_connected():
        print("Подключено к Base network")
        main()
    else:
        print("Ошибка подключения к Base network") 