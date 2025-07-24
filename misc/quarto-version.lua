function getOS()
	-- ask LuaJIT first
	if jit then
		return jit.os
	end

	-- Unix, Linux variants
	local fh,err = assert(io.popen("uname -o 2>/dev/null","r"))
	if fh then
		osname = fh:read()
	end
	
	if osname then
	    return osname
	end
	
	local handle = io.popen("ver")
    local version = handle:read("*a")
    handle:close()

	return osname or version
end

function RawInline (raw)
  if raw.format:match 'html' and raw.text == '<?quarto.version?>'then
      return tostring(quarto.version)..", compiled on "..getOS()
  end
end