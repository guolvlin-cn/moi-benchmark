(a)

(b)

(c)

(d)

Fig. 4. The dispersion contours with step sizes \Delta t = 0.01 , \Delta = 0.1 for Maxwell's equations (46) from (a) exact dispersion; (b) boxscheme; (c) symplectic method and (d) Yee's method. The constant contour values are \omega \in [2,4,6,\dots,24] .

    $$\varphi = \tan^ {- 1} \left(\frac{\left(v _ {g}\right) _ {y}}{\left(v _ {g}\right) _ {x}}\right), \quad \left| v _ {g} \right| = \sqrt{\left(v _ {g}\right) _ {x} ^ {2} + \left(v _ {g}\right) _ {y} ^ {2}}. \tag{48}$$
Substituting into (48) the vectors $\kappa$ and $v_{\mathrm{g}}$ in polar coordinates (44), and let $a = |\kappa| \Delta$, this yields the propagation angle $\varphi$ and the propagation speed $|v_{\mathrm{g}}|$ in terms of $a$ and $\theta$.
  For example, $\varphi$ for the boxscheme is given by
    $$\varphi = \tan^ {- 1} \left(\frac{\sin \left(\frac{1}{2} \sin (\theta) a\right) \cos^ {3} \left(\frac{1}{2} \cos (\theta) a\right)}{\cos^ {3} \left(\frac{1}{2} \sin (\theta) a\right) \sin \left(\frac{1}{2} \cos (\theta) a\right)}\right).$$
Taking the Taylor expansion of this expression with respect to a = 0 yields,

    $$\varphi \approx \theta - \frac{1}{1 2} \sin (4 \theta) a ^ {2} + O \left(a ^ {3}\right). \tag{49}$$
Similarly, the Taylor expansion of $|v_{\mathrm{g}}|$ at $a = 0$ yields,
    $$\left| v _ {g} \right| \approx 1 + \left(\frac{1}{1 6} \cos (4 \theta) - \frac{r ^ {2}}{4} + \frac{3}{1 6}\right) a ^ {2} + O \left(a ^ {4}\right), \tag{50}$$
