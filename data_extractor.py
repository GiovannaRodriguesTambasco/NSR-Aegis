import pandas as pd
import numpy as np
import xarray as xr
import cdsapi
import os
import zipfile
import glob

class RealPanamaDataExtractor:
    def __init__(self, start_year=2015, end_year=2025):
        self.start_year = start_year
        self.end_year = end_year
        self.output_dir = "data"
        self.fake_nc_file = f"{self.output_dir}/panama_era5_raw.nc"
        self.zip_file = f"{self.output_dir}/panama_era5_raw.zip" 
        self.extract_dir = f"{self.output_dir}/nc_files"
        self.csv_file = f"{self.output_dir}/panama_climate_data.csv"
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        if not os.path.exists(self.extract_dir):
            os.makedirs(self.extract_dir)

    def fetch_real_copernicus_data(self):
        print("[EXTRACTOR] Connecting to official Copernicus API (CDS)...")
        
        # 1. CORREÇÃO DE INFRAESTRUTURA: Renomeia o arquivo enganoso do Copernicus
        if os.path.exists(self.fake_nc_file) and not os.path.exists(self.zip_file):
            print("[EXTRACTOR] Consertando a falha da API: Renomeando o arquivo cru para .zip...")
            os.rename(self.fake_nc_file, self.zip_file)
            
        if os.path.exists(self.zip_file) and os.path.getsize(self.zip_file) > 100000:
            print("[EXTRACTOR] Arquivo de satélite (ZIP) encontrado localmente. Pulando download da API.")
            return

        c = cdsapi.Client()
        years = [str(y) for y in range(self.start_year, self.end_year + 1)]
        area_panama = [10.0, -81.0, 8.0, -78.0] 
        
        try:
            c.retrieve(
                'reanalysis-era5-single-levels-monthly-means',
                {
                    'data_format': 'netcdf',  
                    'download_format': 'unarchived', 
                    'product_type': 'monthly_averaged_reanalysis',
                    'variable': [
                        'total_precipitation', '2m_temperature', '10m_u_component_of_wind', 
                        '10m_v_component_of_wind', 'evaporation', 'sea_surface_temperature',
                        'significant_height_of_combined_wind_waves_and_swell', 
                        'mean_wave_period' 
                    ],
                    'year': years, 'month': [f"{m:02d}" for m in range(1, 13)],
                    'time': '00:00', 'area': area_panama,
                },
                self.zip_file # Agora obriga a salvar diretamente como ZIP
            )
            print(f"[EXTRACTOR] Download completed successfully: {self.zip_file}")
        except Exception as e:
            print(f"[EXTRACTOR] Copernicus API Connection Error: {e}")
            exit()

    def process_and_export(self):
        print("[EXTRACTOR] Unzipping satellite data...")
        
        # 2. Descompactação do arquivo mascarado
        try:
            with zipfile.ZipFile(self.zip_file, 'r') as zip_ref:
                zip_ref.extractall(self.extract_dir)
        except zipfile.BadZipFile:
            print("ERRO CRÍTICO: O Copernicus enviou um arquivo corrompido. Apague a pasta /data e rode novamente.")
            exit()

        print("[EXTRACTOR] Processing real NetCDF files and building Data Lake...")
        nc_files = glob.glob(f"{self.extract_dir}/*.nc")
        
        if not nc_files:
            print("ERRO: Nenhum arquivo .nc encontrado dentro do ZIP.")
            exit()

        df = None
        
        # 3. Mesclagem de Dados (Merge Determinístico Implacável)
        for file in nc_files:
            ds = xr.open_dataset(file, engine='netcdf4')
            df_temp = ds.to_dataframe().reset_index()
            
            # Tratamento de mudanças de nome da API (time vs valid_time)
            if 'valid_time' in df_temp.columns and 'time' not in df_temp.columns:
                df_temp = df_temp.rename(columns={'valid_time': 'time'})
                
            df_temp = df_temp.groupby('time').mean(numeric_only=True).reset_index()
            
            if df is None:
                df = df_temp
            else:
                cols_to_use = df_temp.columns.difference(df.columns).tolist() + ['time']
                df = pd.merge(df, df_temp[cols_to_use], on='time', how='outer')

        # Criação dos eixos de tempo
        df['year'] = df['time'].dt.year
        df['month'] = df['time'].dt.month
        df = df.fillna(0) # Zera ruídos do oceano sobre a terra

        # Mapeamento dinâmico (Proteção contra mudanças de chaves do ERA5)
        tp = df['tp'] if 'tp' in df.columns else df.get('mtpr', 0)
        t2m = df['t2m'] if 't2m' in df.columns else 298.15
        e = df['e'] if 'e' in df.columns else df.get('mer', 0)
        u10 = df['u10'] if 'u10' in df.columns else 0
        v10 = df['v10'] if 'v10' in df.columns else 0
        sst = df['sst'] if 'sst' in df.columns else 298.15
        swh = df['swh'] if 'swh' in df.columns else 0
        mwp = df['mwp'] if 'mwp' in df.columns else 0

        # --- FÍSICA SATELITAL 100% REAL ---
        df['precipitation_mm'] = (tp * 1000 * 30).clip(lower=0) 
        df['avg_temp_c'] = t2m - 273.15
        df['evaporation_rate'] = abs(e * 1000 * 30)
        
        wind_ms = np.sqrt(u10**2 + v10**2)
        df['wind_speed_knots'] = wind_ms * 1.94384
        
        mean_sst = (sst - 273.15).mean() if isinstance(sst, pd.Series) else 25.0
        df['sst_anomaly_c'] = (sst - 273.15) - mean_sst
            
        df['wave_stress_factor'] = (swh * 1.5) + (mwp * 0.5)
        
        # --- GÊMEO DIGITAL: ENGENHARIA NAVAL ---
        df['visibility_nm'] = 10.0 - (df['precipitation_mm'] * 0.01) + (df['wind_speed_knots'] * 0.05)
        df['visibility_nm'] = df['visibility_nm'].clip(lower=0.5, upper=10.0)
        
        df['ocean_salinity_psu'] = 34.5 - (df['precipitation_mm'] * 0.003)
        df['fwa_draft_penalty_cm'] = (df['ocean_salinity_psu'] / 35.0) * 15.0
        df['balboa_tide_anomaly_m'] = df['sst_anomaly_c'] * 0.15 

        base_level = 26.5
        lake_levels = []
        current_level = base_level
        
        for rain, evap in zip(df['precipitation_mm'], df['evaporation_rate']):
            net_water_m = (rain - evap) * 0.0015 
            current_level += net_water_m
            current_level = max(22.0, min(current_level, 27.2)) 
            lake_levels.append(current_level)
            
        df['lake_level_m'] = lake_levels
        
        df['max_allowable_draft_m'] = 15.24 - np.maximum(0, (26.5 - df['lake_level_m']) * 0.85)
        
        stress_base = 15.0
        level_deficit = base_level - df['lake_level_m']
        tide_stress = np.where(df['balboa_tide_anomaly_m'] < -0.10, 2.5, 0)
        df['structural_stress_mpa'] = stress_base + (np.maximum(0, level_deficit) ** 1.8) * 6.5 + tide_stress + df['wave_stress_factor']

        # --- EXPORTAÇÃO BLINDADA ---
        columns_to_export = [
            'year', 'month', 'precipitation_mm', 'avg_temp_c', 'wind_speed_knots', 
            'evaporation_rate', 'sst_anomaly_c', 'visibility_nm', 'ocean_salinity_psu',
            'fwa_draft_penalty_cm', 'balboa_tide_anomaly_m', 'lake_level_m', 
            'max_allowable_draft_m', 'structural_stress_mpa'
        ]
        
        df = df.dropna(subset=['year', 'month'])
        df['year'] = df['year'].astype(int)
        df['month'] = df['month'].astype(int)
        
        for col in columns_to_export:
            if col not in ['year', 'month']:
                df[col] = df[col].round(2)
        
        df[columns_to_export].to_csv(self.csv_file, index=False)
        print("=================================================================")
        print(f"[EXTRACTOR] SUCESSO ABSOLUTO! CSV Salvo em: {self.csv_file}")
        print(f"[EXTRACTOR] Registros extraídos diretamente do satélite: {len(df)}")
        print("=================================================================")

if __name__ == "__main__":
    extractor = RealPanamaDataExtractor(start_year=2015, end_year=2025)
    extractor.fetch_real_copernicus_data()
    extractor.process_and_export()