import os
import json
import duckdb
import pandas as pd
import numpy as np
from mcp.server.fastmcp import FastMCP
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score
from statsmodels.tsa.holtwinters import ExponentialSmoothing

mcp = FastMCP("Hyperlytics Forecasting Engine")

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

def get_file_path(filename: str) -> str:
    safe_filename = os.path.basename(filename)
    return os.path.join(DATA_DIR, safe_filename)

@mcp.tool()
def generate_forecast(
    dataset_name: str,
    date_column: str,
    target_column: str,
    horizon_steps: int = 30,
    frequency: str = "auto",
    confidence_level: float = 0.95,
    model_type: str = "auto",
    seasonality_mode: str = "add",
    clean_outliers: bool = False,
    fill_method: str = "interpolate"
) -> str:
    """
    Generates an advanced time-series forecast using Exponential Smoothing or Auto-Regressive Ridge models.
    Supports outlier removal, auto-frequency estimation, and model selection.
    """
    filepath = get_file_path(dataset_name)
    if not os.path.exists(filepath):
        return json.dumps({"error": f"Dataset '{dataset_name}' not found."})

    try:
        # Load data using DuckDB for speed
        con = duckdb.connect(database=':memory:')
        if filepath.endswith('.csv'):
            df = con.execute(f"SELECT \"{date_column}\", \"{target_column}\" FROM read_csv_auto('{filepath}')").df()
        elif filepath.endswith('.parquet'):
            df = con.execute(f"SELECT \"{date_column}\", \"{target_column}\" FROM read_parquet('{filepath}')").df()
        elif filepath.endswith('.json'):
            df = con.execute(f"SELECT \"{date_column}\", \"{target_column}\" FROM read_json_auto('{filepath}')").df()
        elif filepath.endswith('.xlsx'):
            raw_df = pd.read_excel(filepath)
            con.register('excel_tbl', raw_df)
            df = con.execute(f"SELECT \"{date_column}\", \"{target_column}\" FROM excel_tbl").df()
        else:
            return json.dumps({"error": "Unsupported file format."})
        con.close()

        # Parse date and sort
        df[date_column] = pd.to_datetime(df[date_column])
        df = df.sort_values(by=date_column)
        
        # Clean numerical values
        df[target_column] = pd.to_numeric(df[target_column], errors='coerce')
        df = df.dropna(subset=[date_column, target_column])
        
        if len(df) < 10:
            return json.dumps({"error": "Insufficient data points to train a forecasting model. Minimum 10 points required."})
            
        # 1. Frequency Auto Detection
        freq_to_use = frequency
        if frequency == "auto":
            time_diff = df[date_column].diff().dropna().median()
            if time_diff.days >= 28 and time_diff.days <= 31:
                freq_to_use = 'ME'
            elif time_diff.days >= 6 and time_diff.days <= 8:
                freq_to_use = 'W'
            elif time_diff.days == 1:
                freq_to_use = 'D'
            else:
                freq_to_use = 'D'
        
        # Set index and resample
        df = df.set_index(date_column)
        df_resampled = df[target_column].resample(freq_to_use).mean()
        
        # 2. Resampling Fill Method
        if fill_method == "interpolate":
            df_resampled = df_resampled.interpolate(method='linear').ffill().bfill()
        elif fill_method == "ffill":
            df_resampled = df_resampled.ffill().bfill()
        elif fill_method == "bfill":
            df_resampled = df_resampled.bfill().ffill()
        elif fill_method == "zero":
            df_resampled = df_resampled.fillna(0.0)
            
        # 3. Outlier cleaning
        if clean_outliers and len(df_resampled) > 5:
            rolling_mean = df_resampled.rolling(window=min(7, len(df_resampled)), min_periods=1).mean()
            rolling_std = df_resampled.rolling(window=min(7, len(df_resampled)), min_periods=1).std().fillna(df_resampled.std())
            outliers = (df_resampled - rolling_mean).abs() > (3 * rolling_std)
            df_resampled[outliers] = np.nan
            df_resampled = df_resampled.interpolate(method='linear').ffill().bfill()

        # Train-test split for evaluation
        test_size = min(max(3, int(len(df_resampled) * 0.2)), 30)
        train_series = df_resampled.iloc[:-test_size]
        test_series = df_resampled.iloc[-test_size:]
        
        # Define model fitting functions
        def fit_hw(train, test, full, steps, mode):
            s_periods = 7 if freq_to_use == 'D' else (4 if freq_to_use == 'W' else 12)
            use_seasonal = len(train) > (2 * s_periods) and mode != "none"
            
            s_mode = mode if mode in ("add", "mul") else "add"
            if s_mode == "mul" and (train <= 0).any():
                s_mode = "add"
                
            if use_seasonal:
                m = ExponentialSmoothing(train, trend='add', seasonal=s_mode, seasonal_periods=s_periods).fit(optimized=True)
                m_full = ExponentialSmoothing(full, trend='add', seasonal=s_mode, seasonal_periods=s_periods).fit(optimized=True)
            else:
                m = ExponentialSmoothing(train, trend='add', seasonal=None).fit(optimized=True)
                m_full = ExponentialSmoothing(full, trend='add', seasonal=None).fit(optimized=True)
                
            preds = m.forecast(steps=len(test))
            fc = m_full.forecast(steps=steps)
            fitted = m_full.fittedvalues
            return preds, fc, fitted

        def fit_ar_lag(train, test, full, steps):
            lags = [1, 2, 3, 7]
            def make_features(series):
                d_lags = pd.DataFrame(index=series.index)
                d_lags['y'] = series.values
                for lag in lags:
                    d_lags[f'lag_{lag}'] = series.shift(lag)
                return d_lags.dropna()
                
            df_train = make_features(train)
            if len(df_train) < 3:
                raise ValueError("Too few training points for AR model")
                
            reg = Ridge().fit(df_train.drop(columns=['y']).values, df_train['y'].values)
            
            curr = list(train.values)
            preds = []
            for _ in range(len(test)):
                feats = [curr[-lg] for lg in lags]
                p = float(reg.predict([feats])[0])
                preds.append(p)
                curr.append(p)
                
            df_full = make_features(full)
            reg_full = Ridge().fit(df_full.drop(columns=['y']).values, df_full['y'].values)
            
            curr_full = list(full.values)
            fc = []
            for _ in range(steps):
                feats = [curr_full[-lg] for lg in lags]
                p = float(reg_full.predict([feats])[0])
                fc.append(p)
                curr_full.append(p)
                
            fitted = pd.Series(reg_full.predict(df_full.drop(columns=['y']).values), index=df_full.index)
            fitted = pd.concat([full.iloc[:len(full)-len(fitted)], fitted])
            return pd.Series(preds, index=test.index), pd.Series(fc), fitted

        # Model evaluation & selection
        selected_model_name = model_type
        if model_type == "ar_lag":
            test_preds, forecast_values, fitted_values = fit_ar_lag(train_series, test_series, df_resampled, horizon_steps)
        elif model_type == "holt_winters":
            test_preds, forecast_values, fitted_values = fit_hw(train_series, test_series, df_resampled, horizon_steps, seasonality_mode)
        elif model_type == "linear":
            X = np.arange(len(df_resampled)).reshape(-1, 1)
            y = df_resampled.values
            reg = Ridge().fit(X[:-test_size], y[:-test_size])
            test_preds = pd.Series(reg.predict(X[-test_size:]), index=test_series.index)
            
            reg_full = Ridge().fit(X, y)
            future_X = np.arange(len(df_resampled), len(df_resampled) + horizon_steps).reshape(-1, 1)
            forecast_values = pd.Series(reg_full.predict(future_X))
            fitted_values = pd.Series(reg_full.predict(X), index=df_resampled.index)
        else: # Auto Selection
            try:
                hw_preds, hw_fc, hw_fit = fit_hw(train_series, test_series, df_resampled, horizon_steps, seasonality_mode)
                hw_r2 = r2_score(test_series, hw_preds)
            except:
                hw_r2 = -999.0
            
            try:
                ar_preds, ar_fc, ar_fit = fit_ar_lag(train_series, test_series, df_resampled, horizon_steps)
                ar_r2 = r2_score(test_series, ar_preds)
            except:
                ar_r2 = -999.0
                
            if ar_r2 > hw_r2 and ar_r2 > -99:
                test_preds, forecast_values, fitted_values = ar_preds, ar_fc, ar_fit
                selected_model_name = "ar_lag"
            else:
                test_preds, forecast_values, fitted_values = hw_preds, hw_fc, hw_fit
                selected_model_name = "holt_winters"
                
        # Calculate diagnostics
        mae = mean_absolute_error(test_series, test_preds)
        rmse = root_mean_squared_error(test_series, test_preds)
        r2 = r2_score(test_series, test_preds)
        mape = np.mean(np.abs((test_series - test_preds) / test_series)) * 100
        if np.isinf(mape) or np.isnan(mape):
            mape = 0.0

        # Compute dynamic standard deviation of residuals for confidence intervals
        residuals = df_resampled.values - fitted_values.values
        std_error = np.std(residuals) if len(residuals) > 1 else 1.0
        
        # Z-critical value for intervals
        from scipy.stats import norm
        z_val = norm.ppf(1 - (1 - confidence_level) / 2)
        
        # Future dates index
        future_dates = pd.date_range(
            start=df_resampled.index[-1] + pd.tseries.frequencies.to_offset(freq_to_use),
            periods=horizon_steps,
            freq=freq_to_use
        )
        
        # Prepare historical data
        history_list = [
            {"date": date.strftime("%Y-%m-%d"), "value": float(val)}
            for date, val in df_resampled.items()
        ]
        
        # Prepare forecast data with confidence bounds
        forecast_list = []
        for i, (date, val) in enumerate(zip(future_dates, forecast_values)):
            step_std = std_error * np.sqrt(i + 1)
            lower_bound = max(0, val - (z_val * step_std))
            upper_bound = val + (z_val * step_std)
            
            forecast_list.append({
                "date": date.strftime("%Y-%m-%d"),
                "value": float(val),
                "lower_bound": float(lower_bound),
                "upper_bound": float(upper_bound)
            })
            
        return json.dumps({
            "metrics": {
                "mae": float(mae),
                "rmse": float(rmse),
                "mape_percentage": float(mape),
                "r2_score": float(r2),
                "selected_model": selected_model_name
            },
            "history": history_list,
            "forecast": forecast_list,
            "date_column": date_column,
            "target_column": target_column,
            "frequency": freq_to_use
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Forecasting failed: {str(e)}"})

    except Exception as e:
        return json.dumps({"error": f"Forecasting failed: {str(e)}"})

if __name__ == "__main__":
    mcp.run()
