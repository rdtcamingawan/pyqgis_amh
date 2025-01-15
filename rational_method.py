from decimal import Decimal, getcontext
from matplotlib import pyplot as plt

def kirpich(a, d, b, length, slope, c, area):
    tc = 0.0078 * length ** 0.77 * slope**-0.385
    i = a * (tc + d)**b
    q = 0.278 * c * i * area
    return q

def faa(a, d, b, rc, length, slope, c, area):
    slope = slope * 100
    tc = (1.8 * (1.1 - rc) * length**0.5) / slope**0.33
    i = a * (tc + d) **b
    q = 0.278 * c * i * area
    return q

def scs(a, d, b, cn, length, slope, c, area):
    slope = slope * 100
    tc = (100 * length** 0.8 * ((1000 / cn)-9)**0.7) / (1900 * slope**0.5)
    i = a*(tc+d)**b
    q = 0.278 * c * i * area
    return q
   
def i_izzard(a,d,b,length, slope, c, i_iter):
    tc = (41.025 * ((0.0007 * i_iter) + c) * length**0.33) / (slope**(1/3) * i_iter**(2/3))
    i_calc_mm = a * (tc + d)**b
    i_calc = i_calc_mm / 10 / 2.54
    return i_calc , i_iter

def izzard(a,d,b,rc,length,slope,c,area,_threshold):
    lower = 0
    upper = 5000
    solve = (lower + upper) / 2
    threshold = i_izzard(a, d, b, length, slope, rc, solve)[0] - solve  # Compute initial threshold
    
    while abs(threshold) >= _threshold:        
        if threshold < 0:
            upper = solve
        elif threshold > 0:
            lower = solve
        # Update solve based on new bounds
        solve = (lower + upper) / 2
        # Recompute threshold with updated solve
        threshold = i_izzard(a, d, b, l, s, rc, solve)[0] - solve

    tc = (41.025 * ((0.0007 * solve) + rc) * length**0.33) / (slope**(1/3) * solve**(2/3))
    i = a * (tc+d) **b
    q = 0.278 * c * i * area
    
    return q

def i_kinematic(a, d, b, length, slope, n, i_iter):
    # Set precision for calculations
    getcontext().prec = 50  # High precision for critical calculations

    # Convert inputs to Decimal
    a = Decimal(a)
    d = Decimal(d)
    b = Decimal(b)
    length = Decimal(length)
    slope = Decimal(slope)
    n = Decimal(n)
    i_iter = Decimal(i_iter)

    # Perform calculations
    tc = (Decimal("0.94") * (length ** Decimal("0.6") * n ** Decimal("0.6"))) / (
        i_iter ** Decimal("0.4") * slope ** Decimal("0.33")
    )
    i_calc_mm = a * (tc + d) ** b
    i_calc = i_calc_mm / Decimal("10") / Decimal("2.54")
    return i_calc, i_iter

def kinematic(a, d, b, n, length, slope, c, area, _threshold):
    # Set precision for calculations
    getcontext().prec = 50

    # Convert inputs to Decimal
    a = Decimal(a)
    d = Decimal(d)
    b = Decimal(b)
    n = Decimal(n)
    length = Decimal(length)
    slope = Decimal(slope)
    c = Decimal(c)
    area = Decimal(area)
    _threshold = Decimal(_threshold)

    lower = Decimal("0")
    upper = Decimal("1000")
    solve = (lower + upper) / Decimal("2")
    threshold = i_kinematic(a, d, b, length, slope, n, solve)[0] - solve

    threshold_plot = []
    while abs(threshold) >= _threshold:
        if threshold < 0:
            upper = solve
        elif threshold > 0:
            lower = solve
        solve = (lower + upper) / Decimal("2")
        threshold = i_kinematic(a, d, b, length, slope, n, solve)[0] - solve
        threshold_plot.append(threshold)

    tc = (Decimal("0.94") * (length ** Decimal("0.6") * n ** Decimal("0.6"))) / (
        solve ** Decimal("0.4") * slope ** Decimal("0.33")
    )
    i = a * (tc + d) ** b
    q = Decimal("0.278") * c * i * area

    return float(q), float(solve), threshold_plot

# initialize variables
a, d, b = 1666.19, 7.70 ,-0.65
rc = 0.0538	
c = 0.43
n = 0.0647	
cn = 81
l, s, area = 43100, 0.027, 10.65

x = kinematic(a,d,b,n,l,s,c,area,10e-100)
print(x[0])


