def calc_mse(wob_klb, torque_klbft, rpm, rop_ft_hr, bit_diameter_in):
    """Approximate MSE in psi.

    Inputs are WOB in klb, torque in klb-ft, RPM, ROP in ft/hr, and bit
    diameter in inches. This is an advisory calculation, not a command.
    """
    import math

    if rop_ft_hr <= 0 or bit_diameter_in <= 0:
        return None
    area = math.pi * (bit_diameter_in**2) / 4.0
    wob_lbf = wob_klb * 1000.0
    torque_lbf_in = torque_klbft * 1000.0 * 12.0
    rop_in_min = rop_ft_hr * 12.0 / 60.0
    return round((wob_lbf / area) + ((2 * math.pi * rpm * torque_lbf_in) / (area * rop_in_min)), 0)


def optimization_advice(data):
    mse = calc_mse(
        data.get("wob", 0),
        data.get("torque", 0),
        data.get("rpm", 0),
        data.get("rop", 0),
        data.get("bit_diameter", 8.5),
    )
    advice = []
    if mse:
        if mse > 120000:
            advice.append(
                "High MSE: drilling energy is high versus ROP. Check bit wear, dysfunction, poor weight transfer, or formation change."
            )
        elif mse < 60000:
            advice.append("MSE looks reasonable. Continue trending against ROP, torque, WOB, and formation changes.")
        else:
            advice.append("MSE is moderate. Monitor trend; rising MSE with flat/falling ROP may indicate dysfunction or bit dulling.")
    if data.get("rop", 0) <= 0:
        advice.append("ROP is zero or missing; MSE and efficiency calculations need a valid ROP.")
    return mse, advice
