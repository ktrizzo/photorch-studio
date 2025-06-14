import numpy as np
import pandas as pd

def evaluateFvCB(x, p):
    """
    Evaluation of the FvCB (1980) function of photosynthetic assimilation with modified Arrhenius temperature responses.

    Parameters:
    x : numpy.ndarray
        Input array of shape (n, 3), where columns represent [Ci, Q, T] with Ci in umol/mol (or ppm), Q in umol/m2/s and T in K.
    p : pandas.Series or dict
        Parameter set with required keys: Vcmax25, Vcmax_dHa, Vcmax_dHd, Vcmax_Topt,
        Jmax25, Jmax_dHa, Jmax_dHd, Jmax_Topt, Kc25, Kc_dHa, Ko25, Ko_dHa, Gamma25,
        Gamma_dHa, Rd25, Rd_dHa, O, alpha, theta.

    Returns:
    numpy.ndarray
        Net assimilation rates for the given inputs.
    """

    # Ensure p is a dict of scalars
    if isinstance(p, pd.DataFrame):
        p = p.iloc[0].to_dict()
    elif isinstance(p, pd.Series):
        p = p.to_dict()

    # Constants
    R = 0.008314

    # Define Tresp function
    def Tresp(T, dHa, dHd, Topt):
        arrhenius = np.exp(dHa / R * (1 / 298 - 1 / T))
        dHd_over_dHa = max(dHd / dHa,1.0001)
        f298 = 1 + np.exp(dHd / R * (1 / Topt - 1 / 298) - np.log(dHd_over_dHa - 1))
        fT = 1 + np.exp(dHd / R * (1 / Topt - 1 / T) - np.log(dHd_over_dHa - 1))
        return arrhenius * f298 / fT

    # Define temperature-dependent functions
    Vcmax = lambda T: p['Vcmax25'] * Tresp(T, p['Vcmax_dHa'], p['Vcmax_dHd'], p['Vcmax_Topt'])
    Jmax = lambda T: p['Jmax25'] * Tresp(T, p['Jmax_dHa'], p['Jmax_dHd'], p['Jmax_Topt'])
    TPU = lambda T: p['TPU25'] * Tresp(T, p['TPU_dHa'], p['TPU_dHd'], p['TPU_Topt'])
    Kc = lambda T: p['Kc25'] * Tresp(T, p['Kc_dHa'], 500, 1000)
    Ko = lambda T: p['Ko25'] * Tresp(T, p['Ko_dHa'], 500, 1000)
    Gamma = lambda T: p['GammaS25'] * Tresp(T, p['GammaS_dHa'], 500, 1000)
    Rd = lambda T: p['Rd25'] * Tresp(T, p['Rd_dHa'], 500, 1000)
    Kco = lambda T: Kc(T) * (1 + p['O'] / Ko(T))

    # Light response function J
    a = max(p['theta'], 0.0001)  # Ensure 'a' is not zero
    ia = 1 / a  # Reciprocal of a
    J = lambda Q, T: (-(-(p['alpha'] * Q + Jmax(T))) - np.sqrt((-(p['alpha'] * Q + Jmax(T)))**2 - 4 * a * (p['alpha'] * Q * Jmax(T)))) * 0.5 * ia

    # RuBisCO-limited photosynthesis
    vr = lambda Ci, T: Vcmax(T) * ((Ci - Gamma(T)) / (Ci + Kco(T))) - Rd(T)

    # Electron transport-limited photosynthesis
    jr = lambda Ci, Q, T: 0.25 * J(Q, T) * ((Ci - Gamma(T)) / (Ci + 2 * Gamma(T))) - Rd(T)

    # TPU limitation
    alphaG = p['alphaG']
    tpu = lambda Ci, T: 3 * TPU(T) * ((Ci - Gamma(T))/(Ci - (1+3*alphaG) * Gamma(T) ))

    # Smooth hyperbolic minimum
    hmin = lambda f1, f2: (f1 + f2 - np.sqrt((f1 + f2)**2 - 4 * 0.999 * f1 * f2)) / (2 * 0.999)

    # Net assimilation rate
    A = lambda Ci, Q, T: hmin(tpu(Ci, T), hmin(vr(Ci, T), jr(Ci, Q, T)))

    # Inputs
    Ci = x[:, 0]
    Q = x[:, 1]
    T = x[:, 2]

    # Compute assimilation rates
    #return A(Ci, Q, T)

    # Net assimilation rate (given Cc)
    A_given_Cc = lambda Cc, Q, T: hmin(tpu(Cc, T), hmin(vr(Cc, T), jr(Cc, Q, T)))

    # Mesophyll conductance (convert to consistent units if needed)
    gm = p.get('gm', None)

    # Inputs
    Ci = x[:, 0]
    Q = x[:, 1]
    T = x[:, 2]

    A_out = np.zeros_like(Ci)

    for i in range(len(Ci)):
        if gm is None or gm <= 0:
            # If gm is missing or zero, assume Ci = Cc (original behavior)
            A_out[i] = A_given_Cc(Ci[i], Q[i], T[i])
        else:
            # Iteratively solve for Cc such that A(Cc) = gm * (Ci - Cc)
            Ci_i = Ci[i]
            Q_i = Q[i]
            T_i = T[i]

            # Initial guess: Cc = Ci - A / gm, but start with Ci
            Cc = Ci_i - 20/0.2
            for _ in range(40):  # max 20 iterations
                A_i = A_given_Cc(Cc, Q_i, T_i)
                Cc_new = Ci_i - A_i / gm
                if np.abs(Cc_new - Cc) < 1e-6:
                    break
                Cc = Cc_new

            A_out[i] = A_given_Cc(Cc, Q_i, T_i)

    return A_out