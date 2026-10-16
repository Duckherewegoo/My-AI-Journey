# train DWSR baseline

if [ "$1" = "" ]; then
  echo "Please specify \$1."
  exit
fi

cd "../trains_${1}"

# specify CUDA card(s) here
PYTHONPATH=../../ CUDA_VISIBLE_DEVICES=0 python dwsr.py
