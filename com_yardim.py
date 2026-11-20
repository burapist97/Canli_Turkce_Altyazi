"""comtypes'ı hangi iş parçacığından olursa olsun güvenle içe aktarma.

comtypes, İLK içe aktarıldığı iş parçacığında COM'u kendisi açar (sys.coinit_flags; varsayılan tek iş parçacıklı
kip). O iş parçacığında COM daha önce başka kipte açıldıysa (WinRT ses sentezi ve .NET iş parçacıkları çok iş
parçacıklı kipte açar) içe aktarma "İş parçacığı modu kurulduktan sonra değiştirilemez" (RPC_E_CHANGED_MODE)
hatasıyla düşer. 2.4.1 derlemesinin duman testinde gerçekten oldu: Türkçe ses üretildikten sonra aynı iş
parçacığında ses oturumları okunmak istendi.

comtypes_al() iki kipi de dener: iş parçacığının zaten kullandığı kip hangisiyse o başarılı olur.
"""
import sys


def comtypes_al():
    if "comtypes" in sys.modules:
        return sys.modules["comtypes"]
    yok = object()
    eski = getattr(sys, "coinit_flags", yok)
    son_hata = None
    try:
        for kip in (0, 2):  # COINIT_MULTITHREADED, COINIT_APARTMENTTHREADED
            sys.coinit_flags = kip
            try:
                import comtypes
                return comtypes
            except OSError as e:
                son_hata = e
                for ad in [a for a in sys.modules if a == "comtypes" or a.startswith("comtypes.")]:
                    del sys.modules[ad]  # yarım kalan içe aktarma temiz yeniden denensin
        raise son_hata
    finally:
        if eski is yok:
            if hasattr(sys, "coinit_flags"):
                del sys.coinit_flags
        else:
            sys.coinit_flags = eski


def com_ac():
    """Bu iş parçacığında COM'u açar; zaten açıksa (hangi kipte olursa olsun) olduğu gibi kullanılır."""
    comtypes = comtypes_al()
    try:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    except OSError:
        pass  # RPC_E_CHANGED_MODE: iş parçacığı tek iş parçacıklı kipte, sorun değil
    return comtypes
