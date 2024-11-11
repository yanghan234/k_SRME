import numpy as np
import pandas as pd

#from .utils import check_imaginary_freqs

import warnings
import traceback



DFEAULT_LIST2NP_COLS = ['max_stress', 'kappa_TOT_RTA', 'kappa_P_RTA',
       'kappa_C', 'weights', 'q_points', 'frequencies',
       'mode_kappa_TOT','mode_kappa_TOT_ave','kappa_TOT_ave']
       
def fill_na_in_list(lst,y):
    return np.asarray([y if pd.isna(x) else x for x in lst])

def process_benchmark_descriptors(
        df_mlp_filtered,
        df_dft_results,
    ):
    
    #df_mlp_filtered = df_mlp_filtered.map(lambda x: np.array(x) if isinstance(x, list) else x)
    #df_dft_results = df_dft_results.map(lambda x: np.array(x) if isinstance(x, list) else x)
    
    mlp_list2np_cols = [col for col in DFEAULT_LIST2NP_COLS if col in df_mlp_filtered.keys()]
    df_mlp_filtered[mlp_list2np_cols] = df_mlp_filtered[mlp_list2np_cols].map(lambda x: np.array(x))

    dft_list2np_cols = [col for col in DFEAULT_LIST2NP_COLS if col in df_dft_results.keys()]
    df_dft_results[dft_list2np_cols] = df_dft_results[dft_list2np_cols].map(lambda x: np.array(x))


    # Remove precomputed columns
    columns_to_remove = ["SRD","SRE","SRME","DFT_kappa_TOT_ave"]
    if any([col in df_mlp_filtered.keys() for col in columns_to_remove]):
        df_mlp_filtered = df_mlp_filtered.drop(columns=[col for col in columns_to_remove if col in df_mlp_filtered.columns])


    if "kappa_TOT_ave" not in df_mlp_filtered.keys():
        df_mlp_filtered["kappa_TOT_ave"] = df_mlp_filtered['kappa_TOT_RTA'].apply(calculate_kappa_ave)
    if "mode_kappa_TOT_ave" not in df_mlp_filtered.keys():
        df_mlp_filtered["mode_kappa_TOT_ave"] = df_mlp_filtered['mode_kappa_TOT'].apply(calculate_kappa_ave)

    df_mlp_filtered["SRD"] = 2*(df_mlp_filtered["kappa_TOT_ave"] - df_dft_results['kappa_TOT_ave'])/(df_mlp_filtered["kappa_TOT_ave"] + df_dft_results['kappa_TOT_ave'])
    
    # turn temperature list to the first temperature (300K) TODO: allow multiple temperatures to be tested
    df_mlp_filtered["SRD"] = df_mlp_filtered["SRD"].apply(lambda x : x[0] if not isinstance(x,float) else x)

    df_mlp_filtered["SRD"] = df_mlp_filtered["SRD"].fillna(-2)

    df_mlp_filtered["SRE"] = df_mlp_filtered["SRD"].abs()

    df_mlp_filtered["SRME"] = calculate_SRME_dataframes(df_mlp_filtered,df_dft_results)

    
    df_mlp_filtered["DFT_kappa_TOT_ave"] = df_dft_results["kappa_TOT_ave"]
    
    columns_to_remove = ["mode_kappa_TOT"]
    df_mlp_filtered = df_mlp_filtered.drop(columns=[col for col in columns_to_remove if col in df_mlp_filtered.keys()])

    # TODO: Add column reason for SRME = 2

    # TODO: round to 4-5 decimals

    return df_mlp_filtered



def get_metrics(df_mlp_filtered):

    mSRE = df_mlp_filtered["SRE"].mean()
    rmseSRE = ((df_mlp_filtered["SRE"]-mSRE)**2).mean() ** 0.5

    mSRME = df_mlp_filtered["SRME"].mean()
    rmseSRME = ((df_mlp_filtered["SRME"]-mSRME)**2).mean() ** 0.5

    return mSRE, mSRME, rmseSRE, rmseSRME



def calculate_kappa_ave(kappa):

    if np.any((pd.isna(kappa))):
        return np.nan
    else:
        _kappa = np.asarray(kappa)

    try :
        kappa_ave = _kappa[...,:3].mean(axis=-1)
    except Exception as e:
        warnings.warn(f"Failed to calculate kappa_ave: {e!r}")
        warnings.warn(traceback.format_exc())
        return np.nan

    return kappa_ave

def calculate_mode_kappa_TOT(mode_kappa_P_RTA,mode_kappa_C,heat_capacity):
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mode_kappa_C_per_mode = 2*((mode_kappa_C * heat_capacity[:,:,:,np.newaxis,np.newaxis])/(heat_capacity[:,:,:,np.newaxis,np.newaxis]+heat_capacity[:,:,np.newaxis,:,np.newaxis])).sum(axis=2)
    
    mode_kappa_C_per_mode[np.isnan(mode_kappa_C_per_mode)]=0

    mode_kappa_TOT = mode_kappa_C_per_mode + mode_kappa_P_RTA

    return mode_kappa_TOT



def calculate_SRME_dataframes(df_mlp,df_dft):

    srme_list = []
    for idx, row_mlp in df_mlp.iterrows():
        row_dft = df_dft.loc[idx]  
        try:
            if "imaginary_freqs" in row_mlp.keys() and row_mlp["imaginary_freqs"]:
                if row_mlp["imaginary_freqs"] == "True" or row_mlp["imaginary_freqs"] == True :
                    srme_list.append(2)
                    continue
            if "relaxed_space_group_number" in row_mlp.keys():
                if "initial_space_group_number" in row_mlp.keys():
                    if row_mlp["relaxed_space_group_number"] != row_mlp["initial_space_group_number"]:
                        srme_list.append(2)
                        continue
                elif "symm.no" in row_dft.keys():
                    if row_mlp["relaxed_space_group_number"] != row_dft["symm.no"]:
                        srme_list.append(2)
                        continue
            result = calculate_SRME(row_mlp,row_dft)
            srme_list.append(result[0]) # append the first temperature SRME

            #Idea: Multiple temperature tests.
        except Exception as e:
            warnings.warn(f"Failed to calculate SRME for {idx}: {e!r}")
            warnings.warn(traceback.format_exc())
            srme_list.append(2)

    return srme_list


def calculate_SRME(kappas_mlp,kappas_dft):

    if np.all(pd.isna(kappas_mlp["kappa_TOT_ave"])):
        return [2]
    if np.any(pd.isna(kappas_mlp["kappa_TOT_RTA"])):
        return [2] #np.nan
    if np.any(pd.isna(kappas_mlp["weights"])):
        return [2] #np.nan
    if np.any(pd.isna(kappas_dft["kappa_TOT_ave"])):
        return [2] #np.nan
    

    if "mode_kappa_TOT_ave" not in kappas_mlp.keys():
        if "mode_kappa_TOT" in kappas_mlp.keys():
            mlp_mode_kappa_TOT_ave = calculate_kappa_ave(kappas_mlp["mode_kappa_TOT"])
        else:
            mlp_mode_kappa_TOT_ave = calculate_kappa_ave(calculate_mode_kappa_TOT(kappas_mlp))
    else:
        mlp_mode_kappa_TOT_ave = np.asarray(kappas_mlp["mode_kappa_TOT_ave"])
    

    if "mode_kappa_TOT_ave" not in kappas_dft.keys():
        if "mode_kappa_TOT" in kappas_dft.keys():
            dft_mode_kappa_TOT_ave = calculate_kappa_ave(kappas_dft["mode_kappa_TOT"])
        else:
            dft_mode_kappa_TOT_ave = calculate_kappa_ave(calculate_mode_kappa_TOT(kappas_dft))
    else:
        dft_mode_kappa_TOT_ave = np.asarray(kappas_dft["mode_kappa_TOT_ave"])


    # calculating microscopic error for all temperatures
    microscopic_error = (np.abs(
        (mlp_mode_kappa_TOT_ave - dft_mode_kappa_TOT_ave) # reduce ndim by 1
        ).sum( axis=tuple(range(1,mlp_mode_kappa_TOT_ave.ndim)) ) # summing axes
        / kappas_mlp["weights"].sum())
    
    
    SRME = 2 * microscopic_error / (kappas_mlp["kappa_TOT_ave"]+kappas_dft["kappa_TOT_ave"])
    
    return SRME



    

