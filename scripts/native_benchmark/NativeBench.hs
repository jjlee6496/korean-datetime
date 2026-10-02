{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -fno-full-laziness -fno-cse #-}
module Main where

import Control.Exception (evaluate)
import Control.DeepSeq (force)
import Control.Monad (forM_)
import Data.Aeson
import qualified Data.ByteString.Lazy.Char8 as BL
import qualified Data.HashMap.Strict as HM
import Data.Text (Text)
import Data.Time
import Data.Time.Clock.POSIX (posixSecondsToUTCTime)
import Data.Time.LocalTime.TimeZone.Series
import GHC.Clock (getMonotonicTimeNSec)
import Duckling.Core
import Duckling.Data.TimeZone (loadTimeZoneSeries)

-- Only this harness is modified; Duckling source and rules are untouched.
data Request = Request Int Int Text Integer
instance FromJSON Request where
  parseJSON = withObject "Request" $ \o -> Request
    <$> o .: "id" <*> o .: "round" <*> o .: "text" <*> o .: "reftime"

{-# NOINLINE parseBytes #-}
parseBytes :: Text -> Context -> Value
parseBytes text ctx = toJSON $ parse text ctx (Options False) [Seal Time]

main :: IO ()
main = do
  zones <- loadTimeZoneSeries "/usr/share/zoneinfo/"
  contents <- BL.getContents
  forM_ (BL.lines contents) $ \line -> do
    request <- either fail pure (eitherDecode line)
    let Request ident roundNo text ref = request
        ctx = Context (makeReftime zones "Asia/Seoul" (posixSecondsToUTCTime (fromInteger ref / 1000))) (makeLocale KO Nothing)
    -- Decode request and construct reference time outside the timed interval.
    _ <- evaluate (length (show text) + length (show ctx))
    begin <- getMonotonicTimeNSec
    entities <- evaluate (force (parseBytes text ctx))
    parsed <- getMonotonicTimeNSec
    let encoded = encode entities
    bytes <- evaluate (BL.length encoded)
    finish <- getMonotonicTimeNSec
    BL.putStrLn $ encode $ object
      ["id" .= ident, "round" .= roundNo, "ns" .= (finish-begin), "parse_ns" .= (parsed-begin), "bytes" .= bytes, "entities" .= entities]
