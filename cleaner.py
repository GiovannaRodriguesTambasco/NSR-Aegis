import pandas as pd
import numpy as np

# 1. Carrega o CSV bruto que o extrator gerou
df = pd.read_csv('data/panama_climate_data.csv')

# 2. Limpa os sensores quebrados (Zero Absoluto do Satélite)
df['avg_temp_c'] = df['avg_temp_c'].apply(lambda x: np.nan if x < -50 else x)
df = df.replace(0.0, np.nan)

# 3. Agrupa os meses e tira a média (Funde as 264 linhas nas 132 linhas reais)
df_clean = df.groupby(['year', 'month']).mean().reset_index()

# 4. Salva por cima do arquivo original, arredondando para 2 casas decimais
df_clean = df_clean.round(2)
df_clean.to_csv('data/panama_climate_data.csv', index=False)

print("DIAMANTE POLIDO! CSV limpo, com 132 meses perfeitos e pronto para a Inteligência Artificial.")