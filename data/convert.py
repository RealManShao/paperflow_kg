import csv

def convert_entities(input_txt, output_csv):
    """将 all_entity_info.txt 转换为 entities.csv"""
    with open(input_txt, 'r', encoding='utf-8') as fin, \
         open(output_csv, 'w', encoding='utf-8', newline='') as fout:
        
        writer = csv.writer(fout)
        # writer.writerow(['id', 'name', 'type'])  # 写入表头
        
        for line in fin:
            parts = line.strip().split('\t')  # 假设是 Tab 分隔，如果是空格请用 split()
            if len(parts) >= 3:
                # 处理可能存在的多余列或空格
                eid = parts[0].strip()
                name = parts[1].strip()
                etype = parts[2].strip()
                writer.writerow([eid, name, etype])

def convert_relations(input_txt, output_csv):
    """将 train.txt 转换为 relations.csv"""
    with open(input_txt, 'r', encoding='utf-8') as fin, \
         open(output_csv, 'w', encoding='utf-8', newline='') as fout:
        
        writer = csv.writer(fout)
        # writer.writerow(['start_id', 'rel_type', 'end_id'])  # 写入表头
        
        for line in fin:
            parts = line.strip().split('\t') # 假设是 Tab 分隔
            if len(parts) == 3:
                writer.writerow([parts[0].strip(), parts[1].strip(), parts[2].strip()])

# 执行转换
# 请根据实际文件名修改
# convert_entities('data/raw/all_entity_info.txt', 'data/processed/entities.csv')
convert_relations('data/raw/train.txt', 'data/processed/relations.csv')
print("转换完成！")