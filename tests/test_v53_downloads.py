"""Optional keyboard banks can use verified ZIP, TAR and source-file inputs."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from lingfeng.audio import pack_install as installer
from tests.test_v52_pack_install import Response

ROOT=Path(__file__).resolve().parents[1]


class MultiSourceTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'tmp').mkdir(exist_ok=True);self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def zip_bytes(self,entries):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            for name,value in entries.items():z.writestr(name,value)
        return data.getvalue()

    def tar_bytes(self,entries,link=False):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as t:
            for name,value in entries.items():
                item=tarfile.TarInfo(name)
                if link:item.type=tarfile.SYMTYPE;item.linkname='../../outside'
                else:item.size=len(value)
                t.addfile(item,None if link else io.BytesIO(value))
        return data.getvalue()

    def test_tar_extracts_only_selected_regular_files(self):
        source=self.root/'bank.tar.gz';source.write_bytes(self.tar_bytes({'upstream/piano.sf2':b'bank','upstream/unused.txt':b'ignore'}))
        folder=self.root/'pack';folder.mkdir()
        installer._mapped_asset(source,folder,dict(format='tar',file_map={'upstream/piano.sf2':'bank.sf2'}),None)
        self.assertEqual((folder/'bank.sf2').read_bytes(),b'bank')
        self.assertFalse((folder/'unused.txt').exists())

    def test_tar_links_traversal_and_missing_members_fail(self):
        folder=self.root/'pack';folder.mkdir();source=self.root/'bank.tar.gz'
        source.write_bytes(self.tar_bytes({'upstream/link':b''},link=True))
        with self.assertRaises(ValueError):
            installer._mapped_asset(source,folder,dict(format='tar',file_map={'upstream/link':'bank.sf2'}),None)
        source.write_bytes(self.tar_bytes({'upstream/bank':b'bank'}))
        for file_map in ({'upstream/bank':'../outside'},{'missing':'bank.sf2'}):
            with self.assertRaises(ValueError):
                installer._mapped_asset(source,folder,dict(format='tar',file_map=file_map),None)

    def fixture(self):
        binary=bytearray(128);binary[:2]=b'MZ';binary[60:64]=(64).to_bytes(4,'little');binary[64:70]=b'PE\0\0\x64\x86'
        binary=bytes(binary)
        sources=[self.tar_bytes({'fonts/test.sf2':b'test font'}),self.zip_bytes({'release/bin/test.dll':binary}),b'complete engine source']
        assets=[]
        for index,content in enumerate(sources):
            asset=dict(url=f'https://example.org/{index}',sha256=hashlib.sha256(content).hexdigest(),archive_bytes=len(content),format=('tar','zip','file')[index])
            if index==0:asset['file_map']={'fonts/test.sf2':'test.sf2'}
            elif index==1:asset['file_map']={'release/bin/test.dll':'bin/test.dll'}
            else:asset['target']='runtime/source.zip'
            assets.append(asset)
        manifest=dict(schema=1,abi=1,platform='windows-x64',id='test-keyboard',name='测试键盘',name_en='Test keyboard',version='0.53',license='MIT',author='Test',source='https://example.org/',library='bin/test.dll',sha256=hashlib.sha256(binary).hexdigest(),license_file='LICENSE.txt',presets=[dict(program=0,model=0,gain=.3,name='钢琴',name_en='Piano')])
        return sources,dict(id='test-keyboard',assets=assets,archive_bytes=sum(map(len,sources)),manifest=manifest,text_files={'LICENSE.txt':'MIT'})

    def test_multi_source_download_combines_hash_checked_inputs_and_source(self):
        sources,entry=self.fixture();progress=[]
        with patch.object(installer,'urlopen',side_effect=[Response(s) for s in sources]):
            target=installer.install_download(entry,self.root/'installed',progress=lambda a,b:progress.append((a,b)))
        self.assertEqual((target/'test.sf2').read_bytes(),b'test font')
        self.assertEqual((target/'runtime/source.zip').read_bytes(),b'complete engine source')
        self.assertIn((sum(map(len,sources)),sum(map(len,sources))),progress)

    def test_later_source_hash_failure_never_installs_partial_pack(self):
        sources,entry=self.fixture();entry['assets'][1]['sha256']='0'*64
        with patch.object(installer,'urlopen',side_effect=[Response(s) for s in sources]):
            with self.assertRaises(ValueError):installer.install_download(entry,self.root/'installed')
        self.assertEqual(list((self.root/'installed').iterdir()),[])


if __name__=='__main__':unittest.main()
