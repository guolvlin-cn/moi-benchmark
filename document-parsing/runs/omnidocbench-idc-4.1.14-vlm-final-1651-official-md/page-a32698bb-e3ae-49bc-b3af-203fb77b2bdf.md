#       APPENDIX C. PROOF OF LEMMA 3.3

  Here, we provide detailed proof for Lemma 3.3. We only establish (3.17) since the other estimate can be derived through a similar argument. We write $B = B_{\mathfrak{M}}$ for simplicity.
  By using the Littlewood-Paley theorem, we get

    $$\left\| \langle \nabla \rangle^ {\alpha_ {1}} D ^ {\alpha_ {2}} B [ f, g ] \right\| _ {L ^ {l _ {1} ^ {\prime}}} ^ {2} \lesssim \left\| P _ {\leq 1} B [ f, g ] \right\| _ {L ^ {l _ {1} ^ {\prime}}} ^ {2} + \sum_ {N > 1} N ^ {2 \left(\alpha_ {1} + \alpha_ {2}\right)} \left\| P _ {N} B [ f, g ] \right\| _ {L ^ {l _ {1} ^ {\prime}}} ^ {2}, \tag{C.1}$$
where $D^{\alpha_2} = \langle |\nabla|^{\alpha_2}\rangle$ or $D^{\alpha_2} = |\nabla|^{\alpha_2}$ . The first term can be estimated as follows:
        $$\| P _ {\leq 1} B [ f, g ] \| _ {L ^ {l _ {1} ^ {\prime}}} \lesssim \| f \| _ {L ^ {l _ {2}}} \| g \| _ {L ^ {2}}.$$
For the second term, we observe

          $$\left\| P _ {N} B [ f, g ] \right\| _ {L ^ {\iota_ {1} ^ {\prime}}} \lesssim \left\| P _ {N} B \left[ P _ {\leq \frac{N}{8}} f, g \right] \right\| _ {L ^ {\iota_ {1} ^ {\prime}}} + \sum_ {M > \frac{N}{8}} \left\| P _ {N} B \left[ P _ {M} f, g \right] \right\| _ {L ^ {\iota_ {1} ^ {\prime}}}.$$
By using (3.16), we deduce

  $$\| P _ {N} B [ P _ {\leq \frac{N}{8}} f, g ] \| _ {L ^ {l _ {1} ^ {\prime}}} \lesssim \| B [ P _ {\leq \frac{N}{8}} f, P _ {\frac{N}{8} <   . <   8 N} g ] \| _ {L ^ {l _ {1} ^ {\prime}}} \lesssim \| P _ {\leq \frac{N}{8}} f \| _ {L ^ {l _ {2}}} \| P _ {\frac{N}{8} <   . <   8 N} g \| _ {L ^ {2}} \lesssim \| f \| _ {L ^ {l _ {2}}} \sum_ {M \sim N} \| P _ {M} g \| _ {L ^ {2}}.$$
Consequently, we arrive at

      $$\begin{array}{l} \sum_ {N > 1} N ^ {2 \left(\alpha_ {1} + \alpha_ {2}\right)} \| P _ {N} B [ P _ {\leq \frac{N}{8}} f, g ] \| _ {L ^ {l _ {1} ^ {\prime}}} ^ {2} \lesssim \| f \| _ {L ^ {l _ {2}}} ^ {2} \sum_ {N > 1} \left(\sum_ {M \sim N} N ^ {\alpha_ {1} + \alpha_ {2}} \| P _ {M} g \| _ {L ^ {2}}\right) ^ {2} \\ \lesssim \| f \| _ {L ^ {l _ {2}}} ^ {2} \sum_ {M \gtrsim 1} M ^ {2 (\alpha_ {1} + \alpha_ {2})} \| P _ {M} g \| _ {L ^ {2}} ^ {2} \\ \lesssim \| f \| _ {L ^ {l _ {2}}} ^ {2} \| g \| _ {\dot{H} ^ {\alpha_ {1} + \alpha_ {2}}} ^ {2}. \\ \end{array}$$
Meanwhile, we find

    $$\sum_ {M > \frac{N}{8}} \| P _ {N} B [ P _ {M} f, g ] \| _ {L ^ {l _ {1} ^ {\prime}}} \lesssim \sum_ {M > \frac{N}{8}} \| P _ {M} f \| _ {L ^ {2}} \| g \| _ {L ^ {l _ {2}}} \lesssim \sum_ {M > \frac{N}{8}} \frac{1}{M ^ {\alpha_ {1} + \alpha_ {2}}} \| P _ {M} f \| _ {\dot{H} ^ {\alpha_ {1} + \alpha_ {2}}} \| g \| _ {L ^ {l _ {2}}}$$
due to (3.16). Then, it follows that

        $$\begin{array}{l} \sum_ {N > 1} N ^ {2 \left(\alpha_ {1} + \alpha_ {2}\right)} \left(\sum_ {M > \frac{N}{8}} \| P _ {N} B [ P _ {M} f, g ] \| _ {L ^ {\iota_ {1} ^ {\prime}}}\right) ^ {2} \\ \lesssim \sum_ {N > 1} \left(\sum_ {M > \frac{N}{8}} \left(\frac{N}{M}\right) ^ {\alpha_ {1} + \alpha_ {2}} \| P _ {M} f \| _ {\dot{H} ^ {\alpha_ {1} + \alpha_ {2}}} \| g \| _ {L ^ {l _ {2}}}\right) ^ {2} \\ \lesssim \| g \| _ {L ^ {l _ {2}}} ^ {2} \sum_ {N > 1} \left(\sum_ {M > \frac{N}{8}} \left(\frac{N}{M}\right) ^ {\alpha_ {1} + \alpha_ {2}} \sum_ {M > \frac{N}{8}} \left(\frac{N}{M}\right) ^ {\alpha_ {1} + \alpha_ {2}} \| P _ {M} f \| _ {\dot{H} ^ {\alpha_ {1} + \alpha_ {2}}} ^ {2}\right) \\ \lesssim \| g \| _ {L ^ {l _ {2}}} ^ {2} \sum_ {M > \frac{1}{8}} \sum_ {1 <   N <   8 M} \left(\frac{N}{M}\right) ^ {\alpha_ {1} + \alpha_ {2}} \| P _ {M} f \| _ {\dot{H} ^ {\alpha_ {1} + \alpha_ {2}}} ^ {2} \\ \lesssim \| g \| _ {L ^ {l _ {2}}} ^ {2} \sum_ {M > \frac{1}{8}} \| P _ {M} f \| _ {\dot{H} ^ {\alpha_ {1} + \alpha_ {2}}} ^ {2} \\ \end{array}$$
by the Cauchy-Schwartz inequality and the fact that

            $$\sum_ {N <   8 M} \left(\frac{N}{M}\right) ^ {\alpha_ {1} + \alpha_ {2}} \lesssim 1.$$
