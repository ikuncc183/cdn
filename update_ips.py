import os
import requests
import json
import time # 引入 time 模組用於實現延遲

# --- 從 GitHub Secrets 或環境變數讀取配置 ---
# Cloudflare API Token，需要有 DNS 編輯權限
CF_API_TOKEN = os.environ.get('CF_API_TOKEN')
# Cloudflare Zone ID，在域名概述頁面右下角可以找到
CF_ZONE_ID = os.environ.get('CF_ZONE_ID')
# 需要更新的域名，例如 'sub.yourdomain.com'
DOMAIN_NAME = os.environ.get('CF_DOMAIN_NAME')

# --- 在此處直接設置要解析的 IP 數量 ---
# 修改此處的數字來決定要獲取多少個優選 IP
MAX_IPS = 5

# --- 優選 IP 的來源地址 ---
IP_API_URL = 'https://raw.githubusercontent.com/chenhuage/cfipcaiji/refs/heads/main/ip.txt'

# --- Cloudflare API 端點 ---
CF_API_BASE_URL = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records"

# --- HTTP 請求標頭 ---
HEADERS = {
    'Authorization': f'Bearer {CF_API_TOKEN}',
    'Content-Type': 'application/json'
}

def get_preferred_ips():
    """從 API 獲取指定數量的優選 IP"""
    print(f"正在從 {IP_API_URL} 獲取最多 {MAX_IPS} 個優選 IP...")
    
    retry_count = 3
    retry_delay = 10 # 秒
    
    for attempt in range(retry_count):
        try:
            response = requests.get(IP_API_URL, timeout=10)
            response.raise_for_status() # 如果請求失敗 (例如 404, 500)，則會拋出異常
            
            lines = response.text.strip().split('\n')
            
            preferred_ips = []
            for line in lines:
                # 忽略空行和註解行
                if not line.strip() or line.strip().startswith('#'):
                    continue
                
                # 提取 IP 部分 (在 '#' 之前的部分)
                ip_part = line.split('#')[0].strip()
                if ip_part:
                    preferred_ips.append(ip_part)
                
                # 如果已達到所需的 IP 數量，則停止處理
                if len(preferred_ips) >= MAX_IPS:
                    break
            
            if preferred_ips:
                print(f"成功獲取了 {len(preferred_ips)} 個 IP: {preferred_ips}")
                return preferred_ips
            else:
                print("錯誤: 未能從來源解析出任何有效的 IP 地址。")
                return []

        except requests.RequestException as e:
            print(f"錯誤: 請求優選 IP 時發生錯誤: {e}")
            if attempt < retry_count - 1:
                print(f"將在 {retry_delay} 秒後進行第 {attempt + 2} 次嘗試...")
                time.sleep(retry_delay)
            else:
                print("已達到最大重試次數，獲取 IP 失敗。")
                return []

    return []

def get_existing_dns_records():
    """獲取當前域名已有的 A 記錄"""
    print(f"正在查詢域名 {DOMAIN_NAME} 的現有 DNS A 記錄...")
    params = {'type': 'A', 'name': DOMAIN_NAME}
    try:
        response = requests.get(CF_API_BASE_URL, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        records = response.json()['result']
        print(f"查詢到 {len(records)} 條已存在的 A 記錄。")
        return records
    except requests.RequestException as e:
        print(f"錯誤: 查詢 DNS 記錄時發生錯誤: {e}")
        return []
    except (KeyError, json.JSONDecodeError):
        print("錯誤: 解析 DNS 記錄響應失敗。")
        return []


def delete_dns_record(record_id):
    """刪除指定的 DNS 記錄"""
    delete_url = f"{CF_API_BASE_URL}/{record_id}"
    try:
        response = requests.delete(delete_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        print(f"成功刪除記錄: {record_id}")
        return True
    except requests.RequestException as e:
        print(f"錯誤: 刪除記錄 {record_id} 時失敗: {e}")
        return False

def create_dns_record(ip):
    """為給定的 IP 創建一條新的 A 記錄"""
    data = {
        'type': 'A',
        'name': DOMAIN_NAME,
        'content': ip,
        'ttl': 60, # 60 是 Cloudflare 允許的最小 TTL (秒)。1 會被解釋為 "自動"。
        'proxied': False
    }
    try:
        response = requests.post(CF_API_BASE_URL, headers=HEADERS, json=data, timeout=10)
        response.raise_for_status()
        print(f"成功為 IP {ip} 創建 A 記錄。")
        return True
    except requests.RequestException as e:
        print(f"錯誤: 為 IP {ip} 創建 A 記錄時失敗: {e}")
        # 嘗試解析更詳細的錯誤訊息
        try:
            error_details = response.json()
            print(f"Cloudflare 返回的錯誤訊息: {error_details}")
        except (json.JSONDecodeError, AttributeError):
            pass # 如果無法解析 JSON，則不顯示額外訊息
        return False

def main():
    """主執行函數"""
    print("--- 開始更新 Cloudflare 優選 IP ---")
    
    if not all([CF_API_TOKEN, CF_ZONE_ID, DOMAIN_NAME]):
        print("錯誤: 缺少必要的環境變數 (CF_API_TOKEN, CF_ZONE_ID, DOMAIN_NAME)。請檢查 GitHub Secrets 或環境變數配置。")
        return

    new_ips = get_preferred_ips()
    if not new_ips:
        print("未能獲取新的 IP 位址，本次任務終止。")
        return

    existing_records = get_existing_dns_records()

    if existing_records:
        print("\n--- 開始刪除舊的 DNS 記錄 ---")
        for record in existing_records:
            delete_dns_record(record['id'])
    else:
        print("沒有需要刪除的舊記錄。")

    print("\n--- 開始創建新的 DNS 記錄 ---")
    success_count = 0
    for ip in new_ips:
        if create_dns_record(ip):
            success_count += 1
    
    print(f"\n--- 更新完成 ---")
    print(f"成功為 {success_count}/{len(new_ips)} 個 IP 位址創建了 DNS 記錄。")

if __name__ == '__main__':
    main()
