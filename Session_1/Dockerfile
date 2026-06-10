FROM continuumio/miniconda3:latest

RUN conda update -n base -c defaults conda -y && \
    pip install contexttimer pandas numpy pyarrow scikit-learn cvxportfolio ray

CMD ["/bin/bash"]
