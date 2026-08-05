      $$\sigma_ {*} (\mathbf{E}) \leq \sup  _ {\| \mathbf{w} \| = 1} \| \mathbb{E} [ \mathbf{E} \mathbf{w} \mathbf{w} ^ {\top} \mathbf{E} ^ {\top} ] \| ^ {\frac{1}{2}} \leq \max  _ {i \in [ N ]} \sup  _ {\| \mathbf{w} \| = 1} \| \mathbb{E} [ \mathbf{E} _ {i,:} \mathbf{w} \mathbf{w} ^ {\top} \mathbf{E} _ {i,:} ^ {\top} ] \| ^ {\frac{1}{2}} \leq \widetilde{\sigma}, \tag{S.13}$$
      $$R (\mathbf{E}) = \left\| \max _ {i \in [ N ], l \in [ L ]} \| \mathbf{E} _ {i, S _ {l}} \| \right\| _ {\infty} \leq \sqrt{M} B.$$
Then the first inequality in Lemma S.5 follows by plugging these conditions into Proposition 1 with $t = c \log d$ with a sufficiently large constant $c$.
  Similarly, for the second and third inequalities we use

    $$\sigma (\mathbf{E} _ {i,:}) = \max \{\| \mathbb{E} [ \mathbf{E} _ {i,:} ^ {\top} \mathbf{E} _ {i,:} ] \| ^ {\frac{1}{2}}, \| \mathbb{E} [ \mathbf{E} _ {i,:} \mathbf{E} _ {i,:} ^ {\top} ] \| ^ {\frac{1}{2}} \} \leq \max \{\sigma \sqrt{J}, \widetilde{\sigma} \} = \sigma \sqrt{J},$$
        $$v \left(\mathbf{E} _ {i,:}\right) = \left\| \operatorname{C o v} \left(\mathbf{E} _ {i,:}\right) \right\| ^ {\frac{1}{2}} \leq \widetilde{\sigma}, \quad \sigma_ {*} \left(\mathbf{E} _ {i,:}\right) \leq \widetilde{\sigma}, \quad R \left(\mathbf{E} _ {i,:}\right) \leq \sqrt{M} B,$$
and

          $$\sigma \left(\mathbf{E} _ {:, j}\right) = \max  \left\{\| \mathbb{E} \left[ \mathbf{E} _ {:, j} ^ {\top} \mathbf{E} _ {:, j} \right] \| ^ {\frac{1}{2}}, \| \mathbb{E} \left[ \mathbf{E} _ {:, j} \mathbf{E} _ {:, j} ^ {\top} \right] \| ^ {\frac{1}{2}} \right\} \leq \sigma \sqrt{N},$$
              $$v \left(\mathbf{E} _ {:, j}\right) \leq \sigma , \quad \sigma_ {*} \left(\mathbf{E} _ {:, j}\right) \leq \sigma , \quad R \left(\mathbf{E} _ {:, j}\right) \leq B.$$
  Furthermore, for the fourth and fifth inequalities,

      $$\sigma \left(\mathbf{E V} ^ {*}\right) = \max  \left\{\| \mathbb{E} \left[ \mathbf{E V} ^ {*} \mathbf{V} ^ {* ^ {\top}} \mathbf{E} ^ {\top} \right] \| ^ {\frac{1}{2}}, \| \mathbb{E} \left[ \mathbf{V} ^ {* ^ {\top}} \mathbf{E} ^ {\top} \mathbf{E V} ^ {*} \right] \| ^ {\frac{1}{2}} \right\} \leq \widetilde{\sigma} \sqrt{N},$$
                $$v \left(\mathbf{E V} ^ {*}\right) \leq \widetilde{\sigma}, \quad \sigma_ {*} \left(\mathbf{E V} ^ {*}\right) \leq \sigma_ {*} (\mathbf{E}) \overset{\text{(S . 1 3)}} {\leq} \widetilde{\sigma},$$
and with $MK \lesssim ML \asymp J$ we have
    $$\| \mathbb{E} [ \mathbf{E} ^ {\top} \mathbf{U} ^ {*} \mathbf{U} ^ {* \top} \mathbf{E} ] \| = \max  _ {l \in [ L ]} \| \mathbb{E} [ \mathbf{E} _ {:, S _ {l}} ^ {\top} \mathbf{U} ^ {*} \mathbf{U} ^ {* \top} \mathbf{E} _ {:, S _ {l}} ] \| \leq \max  _ {l \in [ L ]} \mathbb{E} \| \mathbf{E} _ {:, S _ {l}} ^ {\top} \mathbf{U} ^ {*} \mathbf{U} ^ {* \top} \mathbf{E} _ {:, S _ {l}} \|$$
                  $$= M \max  _ {j \in [ J ]} \mathbb{E} \left[ \mathbf{E} _ {:, j} ^ {\top} \mathbf{U} ^ {*} \mathbf{U} ^ {* \top} \mathbf{E} _ {:, j} \right] \leq M \sigma^ {2} \| \mathbf{U} ^ {*} \| _ {F} ^ {2} = M K \sigma^ {2},$$
            $$\left\| \mathbb{E} \left[ \mathbf{U} ^ {* ^ {\top}} \mathbf{E E} ^ {\top} \mathbf{U} ^ {*} \right] \right\| \leq \left\| \mathbb{E} \left[ \mathbf{E E} ^ {\top} \right] \right\| \leq \sigma^ {2} J,$$
                $$\sigma \left(\mathbf{E} ^ {\top} \mathbf{U} ^ {*}\right) \leq \sigma \sqrt{J} + \sigma \sqrt{M K},$$
          $$R \left(\mathbf{E} ^ {\top} \mathbf{U} ^ {*}\right) = \left\| \max  _ {i \in [ N ], l \in [ L ]} \| \mathbf{E} _ {i, S _ {l}} ^ {\top} \mathbf{U} _ {i,:} ^ {*} \| \right\| _ {\infty} \leq \sqrt{M} B \| \mathbf{U} ^ {*} \| _ {2, \infty},$$
        $$v \left(\mathbf{E} ^ {\top} \mathbf{U} ^ {*}\right) \leq \max  _ {l \in [ L ]} \left\| \mathbb{E} \left[ \mathbf{E} _ {:, S _ {l}} ^ {\top} \mathbf{U} ^ {*} \mathbf{U} ^ {* \top} \mathbf{E} _ {:, S _ {l}} \right] \right\| ^ {\frac{1}{2}} \leq \sqrt{M K} \sigma ,$$
        $$\sigma_ {*} (\mathbf{U} ^ {* \top} \mathbf{E}) ^ {2} \leq \sigma_ {*} (\mathbf{E}) ^ {2} \overset{\text{b y (S . 1 3)}} {\leq} \widetilde{\sigma} ^ {2} \leq M \sigma^ {2}.$$
