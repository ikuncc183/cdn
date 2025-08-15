# update_ips.py
import os
import requests
import json
import time # 引入 time 模块用于实现延迟

# --- 从 GitHub Secrets 读取配置 ---
# Cloudflare API Token，需要有 DNS 编辑权限
CF_API_TOKEN = os.environ.get('CF_API_TOKEN')
# Cloudflare Zone ID，在域名概述页面右下角可以找到
CF_ZONE_ID = os.environ.get('CF_ZONE_ID')
# 需要更新的域名，例如 'sub.yourdomain.com'
DOMAIN_NAME = os.environ.get('CF_DOMAIN_NAME')
# (可选) 需要解析的IP数量
MAX_IPS = os.environ.get('MAX_IPS')

# --- 优选 IP 的 API 地址 ---
IP_API_URL = 'https://addressesapi.090227.xyz/ip.164746.xyz'

# --- Cloudflare API 端点 ---
CF_API_BASE_URL = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records"

# --- HTTP 请求头 ---
HEADERS = {
    'Authorization': f'Bearer {CF_API_TOKEN}',
    'Content-Type': 'application/json'
}

def get_preferred_ips():
    """从 API 获取优选 IP 列表，并加入了延迟重试机制"""
    print(f"正在从 {IP_API_URL} 获取优选 IP...")
    
    # --- 新增：重试逻辑 ---
    retry_count = 3 # 总共尝试3次
    retry_delay = 10 # 每次重试前等待10秒
    
    for attempt in range(retry_count):
        try:
            response = requests.get(IP_API_URL, timeout=10)
            response.raise_for_status() # 如果请求失败 (例如 429, 500等), 则会抛出异常
            
            # --- 如果请求成功，则处理数据并返回 ---
            lines = response.text.strip().split('\n')
            valid_ips = []
            for line in lines:
                if line.strip():
                    ip_part = line.split('#')[0].strip()
                    if ip_part:
                        valid_ips.append(ip_part)

            if not valid_ips:
                print("警告: 从 API 获取到的内容为空或无效。")
                return [] # 如果 API 返回空内容，直接返回
            
            print(f"成功获取并解析了 {len(valid_ips)} 个优选 IP。")

            if MAX_IPS and MAX_IPS.isdigit():
                max_ips_count = int(MAX_IPS)
                if 0 < max_ips_count < len(valid_ips):
                    print(f"根据 MAX_IPS={max_ips_count} 的设置，将只使用前 {max_ips_count} 个 IP。")
                    return valid_ips[:max_ips_count]
                else:
                    print(f"MAX_IPS 设置为 {max_ips_count}，但该值无效或大于/等于总IP数({len(valid_ips)})，将使用所有IP。")
            
            return valid_ips

        except requests.RequestException as e:
            # --- 如果请求失败 ---
            print(f"错误: 请求优选 IP 时发生错误: {e}")
            if attempt < retry_count - 1:
                print(f"将在 {retry_delay} 秒后进行第 {attempt + 2} 次尝试...")
                time.sleep(retry_delay)
            else:
                print("已达到最大重试次数，获取 IP 失败。")
                return [] # 所有重试都失败后，返回空列表

    return [] # 循环结束后以防万一

def get_existing_dns_records():
    """获取当前域名已有的 A 记录"""
    print(f"正在查询域名 {DOMAIN_NAME} 的现有 DNS A 记录...")
    params = {'type': 'A', 'name': DOMAIN_NAME}
    try:
        response = requests.get(CF_API_BASE_URL, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        records = response.json()['result']
        print(f"查询到 {len(records)} 条已存在的 A 记录。")
        return records
    except requests.RequestException as e:
        print(f"错误: 查询 DNS 记录时发生错误: {e}")
        return []
    except (KeyError, json.JSONDecodeError):
        print("错误: 解析 DNS 记录响应失败。")
        return []


def delete_dns_record(record_id):
    """删除指定的 DNS 记录"""
    delete_url = f"{CF_API_BASE_URL}/{record_id}"
    try:
        response = requests.delete(delete_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        print(f"成功删除记录: {record_id}")
        return True
    except requests.RequestException as e:
        print(f"错误: 删除记录 {record_id} 时失败: {e}")
        return False

def create_dns_record(ip):
    """为给定的 IP 创建一条新的 A 记录"""
    data = {
        'type': 'A',
        'name': DOMAIN_NAME,
        'content': ip,
        'ttl': 60,
        'proxied': False
    }
    try:
        response = requests.post(CF_API_BASE_URL, headers=HEADERS, json=data, timeout=10)
        response.raise_for_status()
        print(f"成功为 IP {ip} 创建 A 记录。")
        return True
    except requests.RequestException as e:
        print(f"错误: 为 IP {ip} 创建 A 记录时失败: {e}")
        return False

def main():
    """主执行函数"""
    print("--- 开始更新 Cloudflare 优选 IP ---")
    
    if not all([CF_API_TOKEN, CF_ZONE_ID, DOMAIN_NAME]):
        print("错误: 缺少必要的环境变量 (CF_API_TOKEN, CF_ZONE_ID, DOMAIN_NAME)。请检查 GitHub Secrets 配置。")
        return

    new_ips = get_preferred_ips()
    if not new_ips:
        print("未能获取新的 IP 地址，本次任务终止。")
        return

    existing_records = get_existing_dns_records()

    if existing_records:
        print("\n--- 开始删除旧的 DNS 记录 ---")
        for record in existing_records:
            delete_dns_record(record['id'])
    else:
        print("没有需要删除的旧记录。")

    print("\n--- 开始创建新的 DNS 记录 ---")
    success_count = 0
    for ip in new_ips:
        if create_dns_record(ip):
            success_count += 1
    
    print(f"\n--- 更新完成 ---")
    print(f"成功为 {success_count}/{len(new_ips)} 个 IP 地址创建了 DNS 记录。")

if __name__ == '__main__':
    main()
